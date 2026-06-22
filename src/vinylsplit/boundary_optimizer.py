from vinylsplit.detection import TrackBoundary


class BoundaryOptimizer:
    """Optimize detected track boundaries using the expected track count."""

    def optimize(
        self,
        boundaries: list[TrackBoundary],
        expected_tracks: int,
    ) -> list[TrackBoundary]:
        """Return the best boundaries for the expected number of tracks."""

        if len(boundaries) <= expected_tracks:
            return boundaries

        #
        # Always keep the first track.
        #
        optimized = [boundaries[0]]

        #
        # Remaining candidates.
        #
        candidates = boundaries[1:]

        #
        # Sort by largest gap from previous boundary.
        #
        candidates.sort(
            key=lambda boundary: boundary.start_time,
        )

        while len(optimized) < expected_tracks and candidates:

            best_index = 0
            best_gap = -1.0

            previous = optimized[-1].start_time

            for index, boundary in enumerate(candidates):
                gap = boundary.start_time - previous

                if gap > best_gap:
                    best_gap = gap
                    best_index = index

            optimized.append(candidates.pop(best_index))

        optimized.sort(key=lambda boundary: boundary.start_time)

        #
        # Renumber tracks.
        #
        for number, boundary in enumerate(optimized, start=1):
            boundary.track_number = number

        return optimized