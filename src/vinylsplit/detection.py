from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from vinylsplit.models import Boundary


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

        selected_candidates, confidence_rows = self.select_candidates_for_expected_boundaries(
            candidates=candidates,
            expected_boundary_times=normalized_expected,
            diagnostics=diagnostics,
        )
        self.last_selection_confidence = confidence_rows

        return self.generate_boundaries_from_selected_candidates(selected_candidates)

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

            boundaries.append(
                TrackBoundary(
                    track_number=len(boundaries) + 1,
                    start_time=start_time,
                    reasons=["Silence detected"],
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
    ) -> tuple[list[SilenceCandidate], list[BoundarySelectionConfidence]]:
        """
        Select silence candidates guided by expected boundary times.

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
        selected_candidates: list[SilenceCandidate] = []
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
            selected_candidates.append(selected)
            last_selected_time = selected.start_time

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
                )
            )

        return selected_candidates, confidence_rows

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

    def generate_boundaries_from_selected_candidates(
        self,
        selected_candidates: list[SilenceCandidate],
    ) -> list[TrackBoundary]:
        """Generate track boundaries from selected silence candidates."""

        boundaries = [
            TrackBoundary(
                track_number=1,
                start_time=0.0,
                reasons=["Recording start boundary"],
            )
        ]

        for candidate in selected_candidates:
            boundaries.append(
                TrackBoundary(
                    track_number=len(boundaries) + 1,
                    start_time=candidate.start_time,
                    reasons=[
                        "Silence detected",
                        "Matches expected track duration",
                    ],
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
