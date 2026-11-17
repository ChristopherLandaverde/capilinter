"""CAPILinter.

Offline checks for Meta Conversions API event payloads.
Author: Christopher Landaverde (FOCO Systems)
"""

__version__ = "0.4.0"

from .core import (
    ValidationIssue,
    ValidationResult,
    find_duplicate_event_ids,
    is_fb_cookie,
    is_sha256,
    validate_capi_payload,
)
from .emq import EMQReport, calculate_emq_score
from .hashing import normalize_and_hash_email, normalize_and_hash_field, normalize_and_hash_phone

__all__ = [
    "EMQReport",
    "ValidationIssue",
    "ValidationResult",
    "calculate_emq_score",
    "find_duplicate_event_ids",
    "is_fb_cookie",
    "is_sha256",
    "normalize_and_hash_email",
    "normalize_and_hash_field",
    "normalize_and_hash_phone",
    "validate_capi_payload",
]
