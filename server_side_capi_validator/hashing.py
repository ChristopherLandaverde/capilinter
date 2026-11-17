"""Normalization and SHA-256 hashing helpers matching Meta CAPI rules."""

import hashlib
import re
import unicodedata

_EXTENSION = re.compile(r"\s*(?:ext\.?|extension|x|#)\s*\d+\s*$", re.IGNORECASE)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    """Trim whitespace and lowercase."""
    return email.strip().lower()


def normalize_phone(phone: str, default_country_code: str = "1") -> str:
    """Digits only, with country code, no '+' and no leading zeros.

    - Fullwidth and other Unicode digits are folded to ASCII.
    - A trailing extension (x12, ext. 12, #12) is dropped.
    - A '(0)' trunk prefix is dropped.
    - A '00' international prefix is treated like '+'.
    - A 10-digit national number without '+' or '00' gets the default
      country code (US/Canada by default).
    """
    raw = _EXTENSION.sub("", unicodedata.normalize("NFKC", phone).strip())
    raw = raw.replace("(0)", "")  # national trunk prefix, e.g. +44 (0)20
    international = raw.startswith("+") or raw.startswith("00")
    digits = re.sub(r"[^0-9]", "", raw).lstrip("0")
    if not international and len(digits) == 10 and default_country_code:
        digits = default_country_code + digits
    return digits


def normalize_field(key: str, value: str) -> str:
    """Normalize a non-email, non-phone user_data field before hashing."""
    text = unicodedata.normalize("NFKC", value).strip().lower()
    if key in ("fn", "ln"):
        return re.sub(r"[^\w]|[\d_]", "", text)
    if key == "ct":
        return re.sub(r"[^a-z]", "", text)
    if key in ("st", "country"):
        return re.sub(r"[^a-z]", "", text)[:2]
    if key == "zp":
        compact = re.sub(r"[\s\-]", "", text)
        return compact[:5] if compact[:5].isdigit() else compact
    if key == "ge":
        return text[:1] if text[:1] in ("f", "m") else text
    if key == "db":
        return re.sub(r"[^0-9]", "", text)
    raise ValueError(f"Unsupported field: {key}")


def normalize_and_hash_email(email: str) -> str:
    return _sha256(normalize_email(email))


def normalize_and_hash_phone(phone: str, default_country_code: str = "1") -> str:
    return _sha256(normalize_phone(phone, default_country_code))


def normalize_and_hash_field(key: str, value: str, default_country_code: str = "1") -> str:
    if key == "em":
        return normalize_and_hash_email(value)
    if key == "ph":
        return normalize_and_hash_phone(value, default_country_code)
    return _sha256(normalize_field(key, value))
