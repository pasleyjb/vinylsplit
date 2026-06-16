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
        minimum_silence_seconds: float = 2.0,
        window_seconds: float = 0.05,
        smoothing_windows: int = 20,
    ) -> None:
        self.silence_threshold = silence_threshold
        self.minimum_silence_seconds = minimum_silence_seconds
        self.window_seconds = window_seconds
        self.smoothing_windows = smoothing_windows

    def detect(self, filename: str) -> list[TrackBoundary]:

        audio, samplerate = self.load_audio(filename)

        mono = self.to_mono(audio)

        rms = self.calculate_rms(mono, samplerate)

        smooth = self.smooth_rms(rms)

        valleys = self.find_valleys(smooth)

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

            chunk = audio[start:start + window]

            if len(chunk) == 0:
                continue

            rms.append(
                np.sqrt(np.mean(chunk ** 2))
            )

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

        minimum_windows = int(
            self.minimum_silence_seconds /
            self.window_seconds
        )

        count = 0

        for i, value in enumerate(smooth):

            if value < self.silence_threshold:
                count += 1
            else:

                if count >= minimum_windows:

                    center = i - (count // 2)

                    valleys.append(center)

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

        for index, valley in enumerate(valleys, start=2):

            boundaries.append(
                TrackBoundary(
                    track_number=index,
                    start_time=valley * self.window_seconds,
                )
            )

        return boundaries