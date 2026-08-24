"""Versioned, non-authoritative integration qualification evidence."""

from .evidence import QualificationRepository, assert_secret_safe, collect_local_evidence
from .models import (
    AuthenticationState,
    CleanupState,
    EvidenceClassification,
    EvidenceCounts,
    EvidenceResult,
    GitIdentity,
    HostIdentity,
    ProductVersions,
    QualificationClaim,
    QualificationEvidence,
    ToolIdentity,
)

__all__ = [
    "AuthenticationState",
    "CleanupState",
    "EvidenceClassification",
    "EvidenceCounts",
    "EvidenceResult",
    "GitIdentity",
    "HostIdentity",
    "ProductVersions",
    "QualificationClaim",
    "QualificationEvidence",
    "QualificationRepository",
    "ToolIdentity",
    "assert_secret_safe",
    "collect_local_evidence",
]
