# vinylsplit
Split and tag full-album vinyl recordings into individual tracks.

## Interactive Review Workflow

`vinylsplit process` pauses after boundary detection and opens an adaptive
interactive track review stage before any files are written.

During review, VinylSplit displays:

- album and artist context
- expected versus detected track count
- overall confidence summary
- validation warnings
- track table with `Start`, `End`, `Length`, and `Status` columns
- improvement suggestions from local reanalysis (when applicable)

The last row always shows `EOF` as the endpoint for the final track.

### Track Status Values

| Status | Meaning |
|--------|---------|
| `AUTO (82%)` | Detected automatically; confidence shown |
| `LOCKED` | Manually positioned by you; will not be moved |
| `VERIFIED` | Explicitly accepted by you |

### Review Commands

- `split` / `accept`: approve the review and continue to split/export
- `cancel` / `quit` / `exit` / `q`: stop processing without writing files
- `edit <track> start <time>`: move the start of a track (locks it)
- `edit <track> end <time>`: move the end of a track (locks the next track)
- `verify <track>`: mark a boundary as verified, or apply a pending suggestion
- `add <time>`: insert a track
- `delete <track>`: remove a track
- `undo`: revert the last edit (restores position and status)
- `redo`: restore the last undone edit
- `list`: redisplay the review
- `help`: show command reference

Every edit immediately locks the affected boundary and redisplays the review.
Undo and redo use immutable snapshots so the full session state is restored.

### Timestamps

All time inputs accept multiple formats:

```
232        seconds
232.5      seconds with fractions
3:52       MM:SS
03:52.500  MM:SS.mmm
00:03:52   HH:MM:SS
```
