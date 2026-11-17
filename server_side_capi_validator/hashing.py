"""Normalization and SHA-256 hashing helpers matching Meta CAPI rules."""

import hashlib
import re


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    """Trim whitespace and lowercase."""
    return email.strip().lower()


def normalize_phone(phone: str, default_country_code: str = "1") -> str:
    """Return digits only, with country code, no '+' (Meta's expected form).

    A 10-digit number without a leading '+' is assumed to be in the
    default country (US/Canada by default).
    """
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    if not raw.startswith("+") and len(digits) == 10 and default_country_code:
        digits = default_country_code + digits
    return digits


def normalize_and_hash_email(email: str) -> str:
    return _sha256(normalize_email(email))


def normalize_and_hash_phone(phone: str, default_country_code: str = "1") -> str:
    return _sha256(normalize_phone(phone, default_country_code))
