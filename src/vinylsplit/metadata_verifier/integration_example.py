"""Integration guide for MetadataVerifier in VinylSplit pipeline.

This module shows how to use MetadataVerifier in place of the current
identification pipeline. It's a reference implementation; actual pipeline
integration should follow the pattern shown here.
"""

import asyncio
from pathlib import Path

from vinylsplit.metadata_verifier import (
    AcoustIDMetadataProvider,
    EmbeddedMetadataProvider,
    FilePropertiesProvider,
    MetadataContext,
    MetadataVerifier,
    MetadataVerifierConfig,
    MusicBrainzProvider,
    UserInputMetadataProvider,
    display_agreement_scores,
    display_verification_report,
)


async def identify_with_verifier(
    source_file: str | Path,
    artist_hint: str | None = None,
    album_hint: str | None = None,
) -> tuple[bool, str]:
    """High-level example: identify an audio file using MetadataVerifier.

    Returns (success, message) tuple.
    """
    source_file = Path(source_file)

    # Step 1: Create verifier with custom config
    config = MetadataVerifierConfig(
        auto_proceed_threshold=0.80,
        conflict_warning_threshold=0.60,
        agreement_threshold=0.70,
        interactive_mode=True,
    )
    verifier = MetadataVerifier(config)

    # Step 2: Register providers in priority order
    verifier.register_provider(UserInputMetadataProvider())
    verifier.register_provider(EmbeddedMetadataProvider())
    verifier.register_provider(AcoustIDMetadataProvider())
    verifier.register_provider(MusicBrainzProvider())
    verifier.register_provider(FilePropertiesProvider())

    # Step 3: Create context (would normally come from pipeline)
    # Note: split_track is None here; in pipeline it would be the actual SplitTrack
    context = MetadataContext(
        source_file=str(source_file),
        split_track=None,  # type: ignore
        user_artist=artist_hint,
        user_album=album_hint,
        previous_evidence=[],
        config=config,
    )

    # Step 4: Run verification
    print(f"Identifying: {source_file.name}")
    try:
        evidence, report = await verifier.process_track(context)
    except Exception as exc:
        return False, f"Verification failed: {exc}"

    # Step 5: Display results
    display_verification_report(report)

    if evidence:
        display_agreement_scores(evidence)

    # Step 6: Decide whether to proceed
    if report.auto_proceed:
        return True, f"Auto-proceeding: {report.recommendation}"

    if report.recommendation_severity == "conflict":
        # In interactive mode, ask user for confirmation
        if config.interactive_mode:
            from vinylsplit.metadata_verifier import confirmation_prompt

            proceed = confirmation_prompt(
                "Proceed with this metadata despite conflicts?",
                default_yes=False,
            )
            return proceed, report.recommendation
        else:
            return False, "Conflicts detected; manual review required"

    return True, report.recommendation


# Example usage (not run automatically)
if __name__ == "__main__":

    async def main():
        """Example: verify a test audio file if available."""
        test_file = Path("./test_audio.flac")

        if test_file.exists():
            success, message = await identify_with_verifier(
                test_file,
                artist_hint="The Beatles",
                album_hint="Abbey Road",
            )
            print(f"\nResult: {'✓ Success' if success else '✗ Failed'}")
            print(f"Message: {message}")
        else:
            print(f"Test file not found: {test_file}")
            print(
                "\nTo use this example, place a FLAC audio file at ./test_audio.flac"
            )

    asyncio.run(main())
