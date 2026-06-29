# VinylSplit Roadmap

## Milestone 2 — Production Review Workflow ✓

- Metadata-guided boundary detection
- Interactive track review before export
- Human-friendly timestamp input (MM:SS, HH:MM:SS, seconds)
- Validation warnings
- Undo / redo

## Milestone 3 — Adaptive Boundary Intelligence ✓

- `BoundaryState` enum: AUTO, LOCKED, VERIFIED, SUGGESTED
- Manual edits immediately lock their boundary
- `AdaptiveReviewState` — serializable session model with immutable snapshots for undo/redo
- `LocalAnalyzer` — post-edit reanalysis of the affected neighborhood only
- `SuggestionEngine` — emits candidate improvements without auto-applying
- `Suggestion` model — informational, always user-approved before applied
- Status column in review table (replaces confidence column)
- `verify <track>` command — mark VERIFIED or apply a suggestion
- Full undo/redo restores BoundaryState, not just position

## Milestone 4 — Planned

- Machine-learning assisted boundary scoring
- Saved session files (resume interrupted reviews)
- GUI front end
- Batch processing
