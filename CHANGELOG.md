# Changelog

## 1.0.0-beta - 2026-07-01

### Added

- Startup wizard flow at launch with persisted source/output defaults.
- Embedded full-screen review editor workflow in the main app.
- Menu-driven file/edit/settings actions for focused workspace operations.
- Exporting indicator light in the bottom player bar.

### Improved

- Review workstation layout with resizable panes and waveform-forward editing.
- Boundary playback behavior (`play from boundary`, `skip next`) and transport controls.
- Startup/loading and in-review UI consistency by reducing top chrome.
- Release export support for FLAC, WAV, and MP3 output formats.

### Fixed

- Blank-screen transition after `Accept Changes` by preserving embedded editor visibility.
- Export metadata hint propagation to improve title and artwork resolution during export.
- Waveform review header clutter and toolbar label cleanup.

## 0.2.0 - 2026-06-17

### Added

- Automatic album splitting using silence detection
- AcoustID fingerprint identification
- MusicBrainz metadata lookup
- Retry engine for failed identifications
- Album consensus detection
- Official track list retrieval
- Automatic recovery of missing track titles
- Automatic renaming of recovered tracks

### Improved

- More reliable split point detection
- Better handling of AcoustID failures
- Improved MusicBrainz integration
- Cleaner processing pipeline

### Fixed

- Fingerprint retry logic
- Boundary detection edge cases
- MusicBrainz lookup failures