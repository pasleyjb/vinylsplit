# VinylSplit Copilot Instructions

## Project

VinylSplit is a Python application that converts full-side vinyl recordings into correctly split, tagged FLAC tracks.

## Priorities

1. Accurate track detection
2. Accurate album identification
3. Lossless audio
4. Correct metadata
5. Maintainable code

## Coding Style

- Python 3.14
- Use pathlib
- Use type hints everywhere practical
- Google-style docstrings
- Small focused functions
- Keep business logic separate from CLI code
- Rich is used only for terminal UI
- Typer powers the CLI

## Audio Rules

- Never resample audio.
- Never reduce audio quality.
- Preserve metadata whenever possible.
- Avoid destructive processing.

## When making changes

Explain architectural changes before implementing them.
Prefer modifying existing code over rewriting working code.