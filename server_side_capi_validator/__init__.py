"""Server-Side CAPI Validator.

Offline checks for Meta Conversions API event payloads.
Author: Christopher Landaverde (FOCO Systems)
"""

__version__ = "0.1.0"

from .core import ValidationIssue, ValidationResult, is_sha256, validate_capi_payload
from .emq import EMQReport, calculate_emq_score
from .hashing import normalize_and_hash_email, normalize_and_hash_phone

__all__ = [
    "validate_capi_payload",
    "ValidationIssue",
    "ValidationResult",
    "is_sha256",
    "calculate_emq_score",
    "EMQReport",
    "normalize_and_hash_email",
    "normalize_and_hash_phone",
]
