from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from vinylsplit.models import Boundary
from vinylsplit.review_candidate import ReviewCandidate, ConfidenceBreakdown


TrackBoundary = Boundary


@dataclass(slots=True)
class SilenceCandidate:
    """Represents a detected silence candidate that may become a boundary."""

    start_time: float
    silence_duration: float


@dataclass(slots=True)
class BoundarySelectionConfidence:
    """Diagnostic and confidence details for a selected metadata-guided boundary."""

    expected_boundary: float
    selected_boundary: float
    silence_duration: float
    distance_from_expected: float
    score: float
    confidence: float
    search_radius: float = 20.0
    """The search radius used to find this candidate (for component decomposition)."""


class TrackDetector:
    """Detect track boundaries in long audio recordings."""

    def __init__(
        self,
        silence_threshold: float = 0.06,
        minimum_silence_seconds: float = 1.2,
        window_seconds: float = 0.05,
        smoothing_windows: int = 20,
        boundary_offset_seconds: float = 0.50,
        adaptive_search_radii: tuple[float, ...] = (20.0, 40.0, 60.0, 90.0),
    ) -> None:
        self.silence_threshold = silence_threshold
        self.minimum_silence_seconds = minimum_silence_seconds
        self.window_seconds = window_seconds
        self.smoothing_windows = smoothing_windows
        self.boundary_offset_seconds = boundary_offset_seconds
        self.adaptive_search_radii = adaptive_search_radii
        self.last_selection_confidence: list[BoundarySelectionConfidence] = []

    def detect(
        self,
        filename: str,
        expected_track_count: int | None = None,
        expected_boundary_times: list[float] | None = None,
        diagnostics: bool = False,
    ) -> list[TrackBoundary]:
        """Detect track boundaries from audio and optional metadata guidance."""

        audio, samplerate = self.load_audio(filename)

        mono = self.to_mono(audio)

        rms = self.calculate_rms(mono, samplerate)

        smooth = self.smooth_rms(rms)

        candidates = self.generate_candidates(smooth)
        print(f"Detected {len(candidates)} silence regions:")

        for candidate in candidates:
            print(f"  {candidate.start_time:.2f} seconds")

        if not expected_boundary_times:
            self.last_selection_confidence = []
            return self.build_boundaries_from_candidates(candidates)

        normalized_expected = self._normalize_expected_boundaries(
            expected_track_count=expected_track_count,
            expected_boundary_times=expected_boundary_times,
        )

        print("\n=== Metadata Alignment Summary ===")
        print(f"Expected boundaries: {len(normalized_expected)}")
        print(f"Silence candidates: {len(candidates)}")

        selected_with_alts, confidence_rows = self.select_candidates_for_expected_boundaries(
            candidates=candidates,
            expected_boundary_times=normalized_expected,
            diagnostics=diagnostics,
        )
        self.last_selection_confidence = confidence_rows

        print(f"Selected boundaries: {len(selected_with_alts)}")
        if len(selected_with_alts) < len(normalized_expected):
            print(f"MISSING: {len(normalized_expected) - len(selected_with_alts)} expected boundaries could not be matched.")
        print("==================================\n")

        return self.generate_boundaries_from_selected_with_alternatives(selected_with_alts, confidence_rows)

    def load_audio(self, filename: str):
        """Load audio samples and sample rate from disk."""

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return sf.read(path)

    def to_mono(self, audio):
        """Convert audio to mono when needed."""

        if audio.ndim == 1:
            return audio

        return np.mean(audio, axis=1)

    def calculate_rms(
        self,
        audio: np.ndarray,
        samplerate: int,
    ) -> np.ndarray:
        """Calculate per-window RMS values."""

        window = int(samplerate * self.window_seconds)

        rms = []

        for start in range(0, len(audio), window):
            chunk = audio[start : start + window]

            if len(chunk) == 0:
                continue

            rms.append(np.sqrt(np.mean(chunk**2)))

        return np.array(rms)

    def smooth_rms(self, rms: np.ndarray) -> np.ndarray:
        """Apply moving-average smoothing to RMS values."""

        kernel = np.ones(self.smoothing_windows)

        kernel /= kernel.sum()

        return np.convolve(
            rms,
            kernel,
            mode="same",
        )

    def find_valleys(self, smooth: np.ndarray) -> list[tuple[int, int]]:
        """Find quiet regions as (start_window, length_windows)."""

        valleys: list[tuple[int, int]] = []

        minimum_windows = int(self.minimum_silence_seconds / self.window_seconds)

        count = 0

        for i, value in enumerate(smooth):
            if value < self.silence_threshold:
                count += 1
            else:
                if count >= minimum_windows:
                    start = i - count

                    valleys.append((start, count))

                count = 0

        return valleys

    def generate_candidates(
        self,
        smooth: np.ndarray,
    ) -> list[SilenceCandidate]:
        """
        Generate silence candidates from the smoothed RMS profile.

        Candidate generation intentionally mirrors existing silence detection
        behavior to preserve no-metadata behavior.
        """

        valleys = self.find_valleys(smooth)

        candidates: list[SilenceCandidate] = []

        for start_window, length_windows in valleys:
            candidates.append(
                SilenceCandidate(
                    start_time=(start_window * self.window_seconds) + self.boundary_offset_seconds,
                    silence_duration=length_windows * self.window_seconds,
                )
            )
        print("\n=== Candidate Summary ===")
        print(f"Total candidates: {len(candidates)}")
        for i, candidate in enumerate(candidates):
            print(
                f"{i+1:2d}: "
                f"{candidate.start_time:8.2f}s  "
                f"silence={candidate.silence_duration:.2f}s"
    )
        print("=========================\n")

        return candidates

    def build_boundaries_from_candidates(
        self,
        candidates: list[SilenceCandidate],
    ) -> list[TrackBoundary]:
        """Build boundaries using legacy behavior when metadata is unavailable."""

        boundaries = [
            TrackBoundary(
                track_number=1,
                start_time=0.0,
                reasons=["Recording start boundary"],
                detection_evidence=["Recording start (locked at 0.0s)"],
            )
        ]

        minimum_track_seconds = 60.0
        last_boundary = 0.0

        for candidate in candidates:
            start_time = candidate.start_time
            # Ignore the needle drop
            if start_time < 10.0:
                continue

            # Ignore boundaries that are too close together
            if (start_time - last_boundary) < minimum_track_seconds:
                continue

            # Build single candidate (the selected one)
            candidates_for_boundary = [
                ReviewCandidate(
                    timestamp=candidate.start_time,
                    confidence=1.0,
                    reason="Silence detected (audio-only)"
                )
            ]
            
            # Build confidence breakdown
            breakdown = ConfidenceBreakdown(
                silence_score=min(1.0, candidate.silence_duration / 6.0),
                distance_score=0.0,  # No metadata guidance
                overall=min(1.0, candidate.silence_duration / 6.0),
            )

            boundaries.append(
                TrackBoundary(
                    track_number=len(boundaries) + 1,
                    start_time=start_time,
                    reasons=["Silence detected"],
                    candidate_boundaries=candidates_for_boundary,
                    detection_evidence=[
                        f"Silence: {candidate.silence_duration:.2f}s",
                        "Method: Audio-only silence detection",
                    ],
                    confidence_breakdown=breakdown,
                )
            )

            last_boundary = start_time

        return boundaries

    def _normalize_expected_boundaries(
        self,
        expected_track_count: int | None,
        expected_boundary_times: list[float],
    ) -> list[float]:
        """Normalize expected boundaries for metadata-guided selection."""

        if expected_track_count is None:
            return expected_boundary_times

        expected_boundary_count = max(expected_track_count - 1, 0)

        return expected_boundary_times[:expected_boundary_count]

    def select_candidates_for_expected_boundaries(
        self,
        candidates: list[SilenceCandidate],
        expected_boundary_times: list[float],
        diagnostics: bool,
    ) -> tuple[list[tuple[SilenceCandidate, list[SilenceCandidate]]], list[BoundarySelectionConfidence]]:
        """
        Select silence candidates guided by expected boundary times.

        Returns tuple of:
        - Selected candidates with their alternate candidates: list of (selected, all_nearby_candidates)
        - Confidence rows for each selection

        Selection rules:
        - One candidate can satisfy at most one expected boundary.
        - A boundary is selected only from real silence candidates.
        - Search radius expands progressively only when required.
        - Selected boundaries remain chronological.
        """

        if not candidates or not expected_boundary_times:
            return [], []

        ordered_candidates = sorted(candidates, key=lambda candidate: candidate.start_time)
        candidate_times = [candidate.start_time for candidate in ordered_candidates]

        used_indexes: set[int] = set()
        selected_with_candidates: list[tuple[SilenceCandidate, list[SilenceCandidate]]] = []
        confidence_rows: list[BoundarySelectionConfidence] = []
        last_selected_time = 0.0

        for expected_boundary in expected_boundary_times:
            selected_result = self._select_candidate_for_expected_boundary(
                expected_boundary=expected_boundary,
                ordered_candidates=ordered_candidates,
                candidate_times=candidate_times,
                used_indexes=used_indexes,
                minimum_boundary_time=last_selected_time,
                diagnostics=diagnostics,
            )

            if selected_result is None:
                continue

            selected_index, selected_radius = selected_result

            used_indexes.add(selected_index)

            selected = ordered_candidates[selected_index]
            last_selected_time = selected.start_time

            # Collect all nearby candidates as alternatives
            nearby_indexes = self._nearby_candidate_indexes(
                expected_boundary=expected_boundary,
                candidate_times=candidate_times,
                search_radius=selected_radius,
            )
            nearby_candidates = [ordered_candidates[idx] for idx in nearby_indexes if idx not in {selected_index}]

            selected_with_candidates.append((selected, nearby_candidates))

            score = self.score_candidate(
                candidate=selected,
                expected_boundary=expected_boundary,
                search_radius=selected_radius,
            )
            distance = abs(selected.start_time - expected_boundary)
            confidence = self.calculate_confidence(
                candidate=selected,
                distance=distance,
                search_radius=selected_radius,
            )

            confidence_rows.append(
                BoundarySelectionConfidence(
                    expected_boundary=expected_boundary,
                    selected_boundary=selected.start_time,
                    silence_duration=selected.silence_duration,
                    distance_from_expected=distance,
                    score=score,
                    confidence=confidence,
                    search_radius=selected_radius,
                )
            )

        return selected_with_candidates, confidence_rows

    def _select_candidate_for_expected_boundary(
        self,
        expected_boundary: float,
        ordered_candidates: list[SilenceCandidate],
        candidate_times: list[float],
        used_indexes: set[int],
        minimum_boundary_time: float,
        diagnostics: bool,
    ) -> tuple[int, float] | None:
        """Select the best available candidate for one expected boundary."""

        for search_radius in self.adaptive_search_radii:
            nearby_indexes = self._nearby_candidate_indexes(
                expected_boundary=expected_boundary,
                candidate_times=candidate_times,
                search_radius=search_radius,
            )

            available_indexes = [
                index
                for index in nearby_indexes
                if index not in used_indexes and ordered_candidates[index].start_time > minimum_boundary_time
            ]

            if diagnostics:
                self._print_diagnostics(
                    expected_boundary=expected_boundary,
                    search_radius=search_radius,
                    indexes=available_indexes,
                    candidates=ordered_candidates,
                )

            if not available_indexes:
                continue

            best_index = max(
                available_indexes,
                key=lambda index: self.score_candidate(
                    candidate=ordered_candidates[index],
                    expected_boundary=expected_boundary,
                    search_radius=search_radius,
                ),
            )

            return best_index, search_radius

        return None

    def _nearby_candidate_indexes(
        self,
        expected_boundary: float,
        candidate_times: list[float],
        search_radius: float,
    ) -> list[int]:
        """Return candidate indexes within ±search_radius of expected boundary."""

        start = bisect_left(candidate_times, expected_boundary - search_radius)
        end = bisect_right(candidate_times, expected_boundary + search_radius)

        return list(range(start, end))

    def score_candidate(
        self,
        candidate: SilenceCandidate,
        expected_boundary: float,
        search_radius: float,
    ) -> float:
        """Score a candidate for one expected boundary."""

        distance = abs(candidate.start_time - expected_boundary)
        distance_score = max(0.0, search_radius - distance)
        silence_score = candidate.silence_duration * 10.0

        return silence_score + distance_score

    def calculate_confidence(
        self,
        candidate: SilenceCandidate,
        distance: float,
        search_radius: float,
    ) -> float:
        """
        Calculate confidence as a 0-1 value.

        Confidence increases for longer silence and decreases as distance grows.
        """

        if search_radius <= 0.0:
            return 0.0

        distance_component = max(0.0, 1.0 - (distance / search_radius))
        silence_component = min(1.0, candidate.silence_duration / 6.0)

        return min(1.0, (0.65 * distance_component) + (0.35 * silence_component))

    def generate_boundaries_from_selected_with_alternatives(
        self,
        selected_with_candidates: list[tuple[SilenceCandidate, list[SilenceCandidate]]],
        confidence_rows: list[BoundarySelectionConfidence],
    ) -> list[TrackBoundary]:
        """Generate boundaries from selected candidates with all alternates and confidence data."""

        boundaries = [
            TrackBoundary(
                track_number=1,
                start_time=0.0,
                reasons=["Recording start boundary"],
                detection_evidence=["Recording start (locked at 0.0s)"],
            )
        ]

        for idx, (selected, alternates) in enumerate(selected_with_candidates):
            # Get confidence info for this boundary
            confidence_info = confidence_rows[idx] if idx < len(confidence_rows) else None
            
            # Build all candidates (selected + alternates)
            all_review_candidates = [
                ReviewCandidate(
                    timestamp=selected.start_time,
                    confidence=1.0,  # Selected gets highest score
                    reason="Best match for expected boundary"
                )
            ]
            
            # Add alternates with their scoring
            for alt in alternates:
                if confidence_info:
                    # Estimate confidence for alternate based on distance
                    alt_distance = abs(alt.start_time - confidence_info.expected_boundary)
                    alt_confidence = self.calculate_confidence(
                        candidate=alt,
                        distance=alt_distance,
                        search_radius=max(1.0, abs(selected.start_time - alt.start_time)),
                    )
                else:
                    alt_confidence = min(1.0, alt.silence_duration / 6.0)
                
                all_review_candidates.append(
                    ReviewCandidate(
                        timestamp=alt.start_time,
                        confidence=alt_confidence,
                        reason="Alternate silence candidate"
                    )
                )
            
            # Sort by confidence descending (selected first)
            all_review_candidates = sorted(all_review_candidates, key=lambda c: c.confidence, reverse=True)
            
            # Build confidence breakdown
            if confidence_info:
                silence_score = min(1.0, selected.silence_duration / 6.0)
                # Properly compute distance component using actual search radius
                distance_score = max(0.0, 1.0 - (confidence_info.distance_from_expected / confidence_info.search_radius))
                breakdown = ConfidenceBreakdown(
                    silence_score=silence_score,
                    distance_score=distance_score,
                    overall=confidence_info.confidence,
                )
                evidence = [
                    f"Silence: {selected.silence_duration:.2f}s",
                    f"Distance from expected: {confidence_info.distance_from_expected:.2f}s",
                    f"Score: {confidence_info.score:.2f}",
                ]
            else:
                silence_score = min(1.0, selected.silence_duration / 6.0)
                breakdown = ConfidenceBreakdown(
                    silence_score=silence_score,
                    distance_score=0.0,
                    overall=silence_score,
                )
                evidence = [
                    f"Silence: {selected.silence_duration:.2f}s",
                ]

            boundaries.append(
                TrackBoundary(
                    track_number=len(boundaries) + 1,
                    start_time=selected.start_time,
                    reasons=[
                        "Silence detected",
                        "Matches expected track duration" if confidence_info else "Audio-guided detection",
                    ],
                    candidate_boundaries=all_review_candidates,
                    detection_evidence=evidence,
                    confidence_breakdown=breakdown,
                    detector_confidence=confidence_info.confidence if confidence_info else silence_score,
                )
            )

        return boundaries

    def _print_diagnostics(
        self,
        expected_boundary: float,
        search_radius: float,
        indexes: list[int],
        candidates: list[SilenceCandidate],
    ) -> None:
        """Print diagnostics for one expected boundary and search radius."""

        print("-" * 50)
        print("Expected Boundary")
        print(f"{expected_boundary:.2f}")
        print("Search Radius")
        print(f"{search_radius:.0f}")
        print("Candidates")

        if not indexes:
            print("None")
            return

        scored_rows: list[tuple[int, float, float]] = []

        for index in indexes:
            candidate = candidates[index]
            distance = abs(candidate.start_time - expected_boundary)
            score = self.score_candidate(
                candidate=candidate,
                expected_boundary=expected_boundary,
                search_radius=search_radius,
            )
            scored_rows.append((index, distance, score))

            print(f"{candidate.start_time:.2f}")
            print(f"Distance: {distance:.2f}")
            print(f"Silence: {candidate.silence_duration:.2f}")
            print(f"Score: {score:.2f}")

        best_index, distance, score = max(scored_rows, key=lambda row: row[2])
        selected = candidates[best_index]
        confidence = self.calculate_confidence(
            candidate=selected,
            distance=distance,
            search_radius=search_radius,
        )

        print("Selected")
        print(f"{selected.start_time:.2f}")
        print("Confidence")
        print(f"{confidence * 100:.0f}%")
        print("-" * 50)
