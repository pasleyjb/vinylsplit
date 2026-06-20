from dataclasses import dataclass

import numpy as np

from vinylsplit.analysis.report import SilenceRegion
from vinylsplit.analysis.rms import RMSAnalysis


@dataclass(slots=True)
class SilenceDetector:
    """Detect continuous silence regions within an RMS profile."""

    minimum_silence_seconds: float = 2.0
    percentile: float = 8.0
    minimum_threshold: float = 0.01

    def detect(
        self,
        rms: RMSAnalysis,
    ) -> tuple[float, list[SilenceRegion]]:
        """
        Detect silence regions.

        Returns
        -------
        (threshold, regions)
        """

        values = rms.values

        threshold = max(
            np.percentile(values, self.percentile),
            self.minimum_threshold,
        )

        minimum_windows = max(
            1,
            int(self.minimum_silence_seconds / rms.window_seconds),
        )

        regions: list[SilenceRegion] = []

        start = None

        for index, value in enumerate(values):
            if value < threshold:
                if start is None:
                    start = index

            else:
                if start is not None:
                    length = index - start

                    if length >= minimum_windows:
                        regions.append(
                            SilenceRegion(
                                start_window=start,
                                end_window=index - 1,
                            )
                        )

                    start = None

        if start is not None:
            length = len(values) - start

            if length >= minimum_windows:
                regions.append(
                    SilenceRegion(
                        start_window=start,
                        end_window=len(values) - 1,
                    )
                )

        return threshold, self.merge_regions(
            regions,
            rms,
        )

    def merge_regions(
        self,
        regions: list[SilenceRegion],
        rms: RMSAnalysis,
    ) -> list[SilenceRegion]:
        """
        Merge silence regions that are very close together.

        Small fluctuations inside a long silence can create
        multiple regions. Those should become one region.
        """

        if not regions:
            return []

        merged = [regions[0]]

        merge_distance = int(3.0 / rms.window_seconds)

        for region in regions[1:]:
            previous = merged[-1]

            if (region.start_window - previous.end_window) <= merge_distance:
                merged[-1] = SilenceRegion(
                    start_window=previous.start_window,
                    end_window=region.end_window,
                )

            else:
                merged.append(region)

        return merged
