# Adaptive Metadata Refinement
### VinylSplit Version 1.1 Design Specification

**Author:** Justin Pasley

**Project:** VinylSplit

**Status:** Design

**Target Release:** Version 1.1.0

---

# Vision

VinylSplit currently detects track boundaries by analyzing the audio waveform and identifying periods of silence.

While this works well for many albums, silence detection alone cannot reliably determine the correct split location in every recording.

The objective of Adaptive Metadata Refinement is to transform VinylSplit from a silence detector into an intelligent track verification system.

Instead of asking:

> "Where is the silence?"

VinylSplit will ask:

> "Which split produces the correct song?"

This fundamentally changes how boundaries are selected.

---

# Design Goals

Adaptive Metadata Refinement shall:

- Preserve existing detection accuracy.
- Improve boundary placement.
- Use metadata as feedback.
- Minimize unnecessary fingerprint requests.
- Operate automatically.
- Require no manual editing for most albums.
- Remain completely compatible with the current review workflow.

---

# High Level Pipeline

```
                 Audio File
                      │
                      ▼
             Silence Detection
                      │
                      ▼
          Candidate Boundary List
                      │
                      ▼
        Adaptive Metadata Refinement
                      │
          ┌───────────┴────────────┐
          │                        │
 MetadataVerifier           AcoustID
          │                        │
          └───────────┬────────────┘
                      │
                Boundary Locked
                      │
                      ▼
               Next Track Search
                      │
                      ▼
              Interactive Review
                      │
                      ▼
                   Export
```

---

# Core Philosophy

Silence Detection should never determine the final boundary.

Its responsibility is only to produce possible boundaries.

Adaptive Metadata Refinement determines which candidate is correct.

---

# Processing Workflow

For each track:

1. Determine current locked start position.
2. Search for nearby silence candidates.
3. Rank candidates by audio quality.
4. Verify each candidate.
5. Lock the first successful candidate.
6. Continue with the next track.

---

# Candidate Search

For every expected boundary:

Search a configurable window around the estimated location.

Example:

```
Expected:
03:42.10

Candidates:

03:41.42
03:41.89
03:42.18
03:42.71
03:43.12
```

These candidates are generated from:

- Silence valleys
- RMS valleys
- Existing detector output

---

# Candidate Verification

Each candidate is evaluated independently.

```
Candidate

↓

Temporary Audio Clip

↓

MetadataVerifier

↓

Confidence >= 98%

YES

LOCK

NO

↓

AcoustID

↓

Match?

YES

LOCK

NO

↓

Next Candidate
```

---

# MetadataVerifier Rules

If MetadataVerifier returns:

```
Confidence >= 98%
```

the candidate is accepted immediately.

No AcoustID lookup is performed.

---

# AcoustID Rules

AcoustID is only used when MetadataVerifier confidence is below the threshold.

If AcoustID successfully identifies the track:

- Lock boundary
- Continue to next track

If no match is found:

- Try the next candidate

---

# Temporary Audio

Temporary clips exist only during verification.

Workflow:

```
Candidate

↓

Temporary FLAC

↓

Verification

↓

Delete Temporary File
```

No temporary files remain after processing.

---

# Fingerprint Cache

Fingerprint results should be cached.

Suggested cache key:

```
Track Start Sample
Track End Sample
```

Repeated verification should never regenerate an identical fingerprint.

---

# Locked Boundaries

Once a boundary has been verified it becomes immutable.

```
Track 1

Verified

↓

LOCKED

↓

Track 2 begins here
```

This greatly reduces the search space.

---

# No Duration Penalties

Adaptive Metadata Refinement intentionally does **not** assume track lengths.

Tracks may legitimately be:

- 5 seconds
- 19 seconds
- 38 seconds
- 20 minutes

Track duration is never used as a penalty.

Instead, expected durations from the selected MusicBrainz release provide guidance only.

---

# Candidate Scoring

Priority:

1. MetadataVerifier
2. AcoustID
3. Silence Quality
4. RMS Valley Strength

No arbitrary duration penalties are applied.

---

# New Modules

Version 1.1 introduces:

```
metadata_refiner.py

candidate_search.py

candidate_scorer.py

fingerprint_cache.py

temp_audio.py
```

---

# Pipeline Integration

Current:

```
Detector

↓

Review

↓

Export
```

Version 1.1:

```
Detector

↓

Metadata Refiner

↓

Review

↓

Export
```

---

# User Experience

The user should not notice additional complexity.

Normal workflow remains:

```
Choose Album

↓

Identify Release

↓

Review

↓

Split
```

Adaptive refinement occurs automatically.

---

# Future Improvements

Potential future enhancements include:

- Parallel candidate verification
- Machine learning candidate ranking
- Spectral transition analysis
- Local fingerprint database
- Waveform visualization
- Automatic retry of failed tracks
- Resume interrupted refinement sessions

---

# Success Criteria

Version 1.1 will be considered successful when:

- Most boundaries are verified without user intervention.
- MetadataVerifier resolves the majority of tracks.
- AcoustID requests are minimized.
- Boundary placement improves over silence-only detection.
- Processing remains deterministic and repeatable.

---

# Guiding Principle

Adaptive Metadata Refinement is not intended to replace silence detection.

Silence detection proposes possibilities.

Metadata verification confirms reality.

The final boundary is chosen because it identifies the correct recording—not merely because it occurs during silence.

This distinction defines the design philosophy of VinylSplit Version 1.1.
