from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class RMSAnalysis:
    """Stores the RMS energy profile of an audio recording."""

    values: np.ndarray
    sample_rate: int
    window_seconds: float

    @property
    def window_samples(self) -> int:
        """Number of samples represented by one RMS window."""
        return int(self.sample_rate * self.window_seconds)

    @property
    def duration(self) -> float:
        """Duration represented by the RMS analysis."""
        return len(self.values) * self.window_seconds


class RMSAnalyzer:
    """Calculate RMS energy over fixed-size windows."""

    def __init__(
        self,
        window_seconds: float = 0.050,
    ) -> None:
        self.window_seconds = window_seconds

    def calculate(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> RMSAnalysis:
        """
        Calculate RMS energy across the recording.

        Parameters
        ----------
        audio
            Mono audio samples.

        sample_rate
            Audio sample rate.

        Returns
        -------
        RMSAnalysis
            RMS energy profile.
        """

        window_size = max(
            1,
            int(sample_rate * self.window_seconds),
        )

        values = []

        for start in range(0, len(audio), window_size):
            window = audio[start : start + window_size]

            if len(window) == 0:
                continue

            rms = np.sqrt(np.mean(np.square(window)))

            values.append(float(rms))

        return RMSAnalysis(
            values=np.asarray(values),
            sample_rate=sample_rate,
            window_seconds=self.window_seconds,
        )

    def smooth(
        self,
        rms: RMSAnalysis,
        windows: int = 20,
    ) -> RMSAnalysis:
        """
        Smooth an RMS profile using a moving average.
        """

        kernel = np.ones(windows, dtype=float)
        kernel /= kernel.sum()

        smoothed = np.convolve(
            rms.values,
            kernel,
            mode="same",
        )

        return RMSAnalysis(
            values=smoothed,
            sample_rate=rms.sample_rate,
            window_seconds=rms.window_seconds,
        )
