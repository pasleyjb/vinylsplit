"""
# MetadataVerifier Implementation Guide

## Overview

The MetadataVerifier system has been implemented in `src/vinylsplit/metadata_verifier/` with the following components:

### 1. Data Models (`models.py`)

**Core Enums & Dataclasses:**
- `MetadataSource`: Enum of all evidence sources (USER_INPUT, EMBEDDED_TAGS, ACOUSTID, MUSICBRAINZ, etc.)
- `MetadataEvidence`: Single piece of metadata from one source (includes confidence, reasoning, timestamp)
- `ReleaseEvidenceSet`: All evidence about one release with aggregate scores (agreement, confidence)
- `MetadataConflict`: Disagreement between sources on a field (with severity assessment)
- `VerificationReport`: Final report on a track/album (auto-proceed decision, conflicts, recommendation)
- `MetadataContext`: Shared context during evidence gathering (file path, user hints, config)
- `MetadataVerifierConfig`: Configuration for verification behavior (thresholds, timeouts, etc.)
- `MetadataSourceProvider`: Abstract base class for all metadata providers

### 2. Core Verifier (`verifier.py`)

**MetadataVerifier Class Methods:**
- `register_provider(provider)`: Register a metadata source
- `gather_evidence(context)`: Collect evidence from all providers in parallel
- `verify_release(evidence)`: Analyze evidence, detect conflicts, produce report
- `process_track(context)`: High-level workflow (gather → verify → return results)

**Scoring Logic:**
- Majority voting for consensus values (artist, album, year, track count)
- Agreement scores per field (% of sources that agree with consensus)
- Overall confidence as weighted average of source confidences
- Conflict detection with severity assessment (low/medium/high)
- Auto-proceed threshold (default 80%): if confidence >= threshold and no conflicts, auto-proceed

### 3. Built-in Providers (`providers.py`)

**6 Core Providers:**

1. **UserInputMetadataProvider** (confidence 70%)
   - Uses `--artist` and `--album` CLI arguments
   - Searches MusicBrainz for matching release
   - Source: User intent via CLI

2. **EmbeddedMetadataProvider** (confidence 65%)
   - Reads FLAC Vorbis comment tags (ARTIST, ALBUM, DATE, TRACKTOTAL)
   - Extracts year from DATE field
   - Source: File metadata tags

3. **AcoustIDMetadataProvider** (confidence 85%)
   - Fingerprints audio file
   - Looks up via AcoustID web service
   - Returns match with confidence score
   - Source: Acoustic fingerprint

4. **MusicBrainzProvider** (confidence 90%)
   - Searches MusicBrainz release database
   - Uses user artist/album hints
   - Returns best match with full tracklist
   - Source: Official music database

5. **AlbumResolverProvider** (confidence 80%)
   - Currently returns None; designed for consensus from multiple track IDs
   - Source: Album resolver consensus

6. **FilePropertiesProvider** (confidence 95%)
   - Extracts file duration and properties
   - Marked as required (failure is pipeline error)
   - Source: File system properties

### 4. UI Components (`ui.py`)

**Display Functions:**
- `display_verification_report(report)`: Main report display with colored panels
- `display_conflicts(conflicts)`: Conflict summary table
- `display_evidence_summary(evidence_set)`: Evidence details table
- `display_agreement_scores(evidence_set)`: Agreement scores with visual bars
- `confirmation_prompt(message, default_yes)`: Interactive user prompt

### 5. Integration Example (`integration_example.py`)

Shows how to:
1. Create verifier with custom config
2. Register providers in priority order
3. Build MetadataContext
4. Run `process_track()` async workflow
5. Display results and handle auto-proceed vs. conflicts

## Integration into Pipeline (Next Steps)

### Phase 4: Pipeline Integration

To integrate MetadataVerifier into the main processing pipeline:

1. **Modify `Pipeline.process()` method:**
   ```python
   async def process(self, ...):
       # Instead of:
       # album_match, tracks = self.smart_identifier.identify(...)
       
       # Do:
       # Create MetadataContext with split tracks
       context = MetadataContext(
           source_file=file_path,
           split_track=current_track,
           user_artist=artist,
           user_album=album,
           previous_evidence=gathered_evidence,
           config=self.verifier_config,
       )
       
       # Run verification
       evidence, report = await self.verifier.process_track(context)
       
       # Display verification report
       display_verification_report(report)
       
       # Use evidence.consensus_* for metadata
   ```

2. **Update CLI to use MetadataVerifier:**
   - Modify `pipeline.process()` call to await async verification
   - Pass MetadataVerifierConfig from CLI arguments
   - Wire conflict display to existing Rich UI

3. **Add Configuration Options:**
   - `--confidence-threshold`: Set auto-proceed threshold (default 0.80)
   - `--require-confirmation`: Require user approval for all releases
   - `--evidence-log`: Log all gathered evidence to file
   - `--no-interactive`: Disable interactive conflict resolution

4. **Database/Cache Integration (Future):**
   - Add cache_dir to MetadataVerifierConfig
   - Implement caching of verification results
   - Add LocalCacheProvider for previously verified releases

## Testing Strategy

### Unit Tests (Todo)
1. Test each provider in isolation
2. Test scoring logic (majority vote, agreement calculation)
3. Test conflict detection (edge cases)
4. Test async gathering (timeouts, errors)

### Integration Tests (Todo)
1. End-to-end workflow with mock providers
2. Real audio file identification
3. Conflict resolution scenarios
4. Performance (gathering time, memory)

### Manual Testing
- Use `tools/test_metadata_verifier.py` for smoke tests
- Use `integration_example.py` for workflow testing
- Test with real vinyl audio files

## Configuration Examples

### Default (Strict)
```python
MetadataVerifierConfig(
    auto_proceed_threshold=0.80,
    conflict_warning_threshold=0.60,
    agreement_threshold=0.70,
    require_user_confirmation=False,
    interactive_mode=True,
    gather_timeout=30.0,
)
```

### Lenient (Higher Trust in Sources)
```python
MetadataVerifierConfig(
    auto_proceed_threshold=0.70,
    conflict_warning_threshold=0.50,
    agreement_threshold=0.60,
    require_user_confirmation=False,
    interactive_mode=True,
    gather_timeout=60.0,
)
```

### Automatic (No User Interaction)
```python
MetadataVerifierConfig(
    auto_proceed_threshold=0.75,
    conflict_warning_threshold=0.50,
    agreement_threshold=0.65,
    require_user_confirmation=True,  # Requires explicit approval
    interactive_mode=False,
    gather_timeout=30.0,
)
```

## API Stability

**Stable (Safe to use in production):**
- All dataclasses (MetadataEvidence, ReleaseEvidenceSet, etc.)
- MetadataVerifier.gather_evidence() / verify_release() / process_track()
- UI display functions
- Built-in providers (public API is stable)

**Experimental (Subject to change):**
- MetadataSourceProvider interface (methods may be added)
- Conflict detection logic (scoring may be refined)
- UI styling and layout

## Future Enhancements

1. **Phase 5: Provider Expansion**
   - DiscogsMetadataProvider (API integration)
   - LocalDatabaseProvider (user's personal music library)
   - ReleaseCacheProvider (remember previous verifications)

2. **Phase 6: Advanced Conflict Resolution**
   - Interactive UI for choosing between conflicting claims
   - Support for partial metadata acceptance
   - "Trust this source" user preferences

3. **Phase 7: Performance Optimization**
   - Provider result caching
   - Parallel provider timeouts (faster failure)
   - Incremental evidence gathering (stop early if confident)

4. **Phase 8: Audit Trail & Analytics**
   - Log all evidence to JSON for audit
   - Track verification accuracy over time
   - Identify sources that frequently conflict

## File Structure

```
src/vinylsplit/metadata_verifier/
├── __init__.py                  # Public API exports
├── models.py                    # Data models & enums
├── verifier.py                  # Core MetadataVerifier class
├── providers.py                 # 6 built-in providers
├── ui.py                        # Rich UI components
└── integration_example.py       # Example usage & integration guide

tools/
└── test_metadata_verifier.py    # Smoke tests (Phase 1-2 validation)
```

## Debugging Tips

1. **Enable Evidence Logging:**
   ```python
   config.log_all_evidence = True
   ```

2. **Increase Timeout for Slow Networks:**
   ```python
   config.gather_timeout = 60.0  # seconds
   ```

3. **Test Individual Providers:**
   ```python
   provider = AcoustIDMetadataProvider()
   evidence = await provider.gather(context)
   print(evidence)
   ```

4. **Inspect Verification Report:**
   ```python
   report = await verifier.verify_release(evidence_set)
   print(f"Auto-proceed: {report.auto_proceed}")
   print(f"Conflicts: {len(report.conflicts)}")
   print(f"Recommendation: {report.recommendation}")
   ```

## Known Limitations

1. **Async Requirements:** MetadataVerifier is fully async; requires await in pipeline
2. **No Multi-Release Support:** Currently returns best-match release; doesn't handle "multiple interpretations"
3. **No Interactive Merge:** User can't manually combine conflicting metadata
4. **Fixed Confidence Scores:** Providers have fixed default confidence; may not reflect real-world accuracy
5. **File Properties Provider:** Currently requires SplitTrack context; won't work standalone

## Next Steps for Users

1. Review [METADATA_VERIFIER_DESIGN.md](../docs/METADATA_VERIFIER_DESIGN.md) for architecture
2. Run smoke tests: `python3 tools/test_metadata_verifier.py`
3. Review `integration_example.py` for usage patterns
4. Integrate into pipeline following Phase 4 guidelines above
5. Add unit tests for each provider
"""

__doc__ = __doc__.strip()
