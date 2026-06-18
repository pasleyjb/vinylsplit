from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass
class TrackBoundary:
    """Represents the start of a detected track."""

    track_number: int
    start_time: float


class TrackDetector:
    """Detect track boundaries in long audio recordings."""

    def __init__(
        self,
        silence_threshold: float = 0.06,
        minimum_silence_seconds: float = 1.2,
        window_seconds: float = 0.05,
        smoothing_windows: int = 20,
        boundary_offset_seconds: float = 0.50,
    ) -> None:
        self.silence_threshold = silence_threshold
        self.minimum_silence_seconds = minimum_silence_seconds
        self.window_seconds = window_seconds
        self.smoothing_windows = smoothing_windows
        self.boundary_offset_seconds = boundary_offset_seconds

    def detect(self, filename: str) -> list[TrackBoundary]:

        audio, samplerate = self.load_audio(filename)

        mono = self.to_mono(audio)

        rms = self.calculate_rms(mono, samplerate)

        smooth = self.smooth_rms(rms)

        valleys = self.find_valleys(smooth)
        print(f"Detected {len(valleys)} silence regions:")

        for valley in valleys:
            print(f"  {valley * self.window_seconds:.2f} seconds")

        return self.build_boundaries(valleys)

    def load_audio(self, filename: str):

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return sf.read(path)

    def to_mono(self, audio):

        if audio.ndim == 1:
            return audio

        return np.mean(audio, axis=1)

    def calculate_rms(
        self,
        audio: np.ndarray,
        samplerate: int,
    ) -> np.ndarray:

        window = int(samplerate * self.window_seconds)

        rms = []

        for start in range(0, len(audio), window):
            chunk = audio[start : start + window]

            if len(chunk) == 0:
                continue

            rms.append(np.sqrt(np.mean(chunk**2)))

        return np.array(rms)

    def smooth_rms(self, rms: np.ndarray) -> np.ndarray:

        kernel = np.ones(self.smoothing_windows)

        kernel /= kernel.sum()

        return np.convolve(
            rms,
            kernel,
            mode="same",
        )

    def find_valleys(self, smooth: np.ndarray) -> list[int]:
        """Find quiet regions."""

        valleys = []

        minimum_windows = int(self.minimum_silence_seconds / self.window_seconds)

        count = 0

        for i, value in enumerate(smooth):
            if value < self.silence_threshold:
                count += 1
            else:
                if count >= minimum_windows:
                    start = i - count

                    valleys.append(start)

                count = 0

        return valleys

    def build_boundaries(
        self,
        valleys: list[int],
    ) -> list[TrackBoundary]:

        boundaries = [
            TrackBoundary(
                track_number=1,
                start_time=0.0,
            )
        ]

        minimum_track_seconds = 60.0
        last_boundary = 0.0

        for valley in valleys:
            start_time = valley * self.window_seconds + self.boundary_offset_seconds
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
                )
            )

            last_boundary = start_time

        return boundaries
