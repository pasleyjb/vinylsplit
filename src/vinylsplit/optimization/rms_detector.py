from __future__ import annotations

import numpy as np

from vinylsplit.analysis.rms import RMSAnalysis


class RMSValleyDetector:
    """Detect local RMS valleys and provide normalized valley scores."""

    def __init__(self, lookaround_windows: int = 5) -> None:
        self._lookaround = max(1, lookaround_windows)

    def valley_score(self, rms: RMSAnalysis, time_seconds: float) -> float:
        """Return a normalized valley score in [0, 1] for a timestamp."""
        if len(rms.values) == 0:
            return 0.0

        center = self._time_to_index(rms, time_seconds)
        left = max(0, center - self._lookaround)
        right = min(len(rms.values) - 1, center + self._lookaround)

        neighborhood = rms.values[left : right + 1]
        if len(neighborhood) == 0:
            return 0.0

        local_max = float(np.max(neighborhood))
        local_min = float(np.min(neighborhood))
        center_value = float(rms.values[center])

        span = max(1e-9, local_max - local_min)
        score = (local_max - center_value) / span
        return float(np.clip(score, 0.0, 1.0))

    @staticmethod
    def _time_to_index(rms: RMSAnalysis, time_seconds: float) -> int:
        idx = int(time_seconds / rms.window_seconds)
        return int(np.clip(idx, 0, len(rms.values) - 1))
