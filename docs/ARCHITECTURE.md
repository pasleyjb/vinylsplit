
# VinylSplit Architecture

## Philosophy

VinylSplit separates user interfaces from the processing engine.

This allows multiple front ends (CLI, GUI, or future integrations) to share the same core functionality.

## System Architecture

```mermaid
flowchart TD
    CLI["CLI (Typer)"]
    GUI["GUI (VinylSplit Studio)"]
    API["Future API"]

    CLI --> Pipeline
    GUI --> Pipeline
    API --> Pipeline

    Pipeline --> Audio
    Pipeline --> Lookup
    Pipeline --> Detection
    Pipeline --> Splitting
    Pipeline --> Metadata
    Pipeline --> Artwork

    Audio["audio.py"]
    Lookup["lookup.py"]
    Detection["detector.py"]
    Splitting["splitter.py"]
    Metadata["metadata.py"]
    Artwork["artwork.py"]
```

## Design Principles

- One responsibility per module.
- Business logic never depends on the user interface.
- The original recording is never modified.
- Every feature should be testable.
- The CLI and GUI must use the same processing pipeline.