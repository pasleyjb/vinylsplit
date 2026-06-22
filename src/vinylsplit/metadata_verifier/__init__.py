"""VinylSplit Metadata Verifier: Evidence-based metadata verification system."""

from vinylsplit.metadata_verifier.models import (
    MetadataContext,
    MetadataConflict,
    MetadataEvidence,
    MetadataSource,
    MetadataSourceProvider,
    MetadataVerifierConfig,
    ReleaseEvidenceSet,
    VerificationReport,
)
from vinylsplit.metadata_verifier.providers import (
    AcoustIDMetadataProvider,
    AlbumResolverProvider,
    EmbeddedMetadataProvider,
    FilePropertiesProvider,
    MusicBrainzProvider,
    UserInputMetadataProvider,
)
from vinylsplit.metadata_verifier.ui import (
    confirmation_prompt,
    display_agreement_scores,
    display_conflicts,
    display_evidence_summary,
    display_verification_report,
)
from vinylsplit.metadata_verifier.verifier import MetadataVerifier

__all__ = [
    "MetadataContext",
    "MetadataConflict",
    "MetadataEvidence",
    "MetadataSource",
    "MetadataSourceProvider",
    "MetadataVerifierConfig",
    "ReleaseEvidenceSet",
    "VerificationReport",
    "MetadataVerifier",
    "UserInputMetadataProvider",
    "EmbeddedMetadataProvider",
    "AcoustIDMetadataProvider",
    "MusicBrainzProvider",
    "AlbumResolverProvider",
    "FilePropertiesProvider",
    "display_verification_report",
    "display_conflicts",
    "display_evidence_summary",
    "display_agreement_scores",
    "confirmation_prompt",
]
