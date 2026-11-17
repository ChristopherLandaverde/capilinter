"""Normalization and SHA-256 hashing helpers matching Meta CAPI rules."""

import datetime
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


def _letters_only(text: str) -> str:
    """Lowercase letters only; keeps UTF-8 letters such as 'é' (Meta: no punctuation, digits or spaces)."""
    return "".join(ch for ch in text if ch.isalpha())


def _normalize_dob(text: str) -> str:
    """Return YYYYMMDD. Accepts YYYY-MM-DD, M/D/YYYY (US, as in Meta's example), D/M/YYYY when day > 12, or YYYYMMDD."""
    groups = re.findall(r"\d+", text)
    if len(groups) == 1 and len(groups[0]) == 8:
        year, month, day = groups[0][:4], groups[0][4:6], groups[0][6:]
    elif len(groups) == 3 and len(groups[0]) == 4:
        year, month, day = groups
    elif len(groups) == 3 and len(groups[2]) == 4:
        first, second, year = groups
        month, day = (second, first) if int(first) > 12 >= int(second) else (first, second)
    else:
        raise ValueError(f"db must be a date such as 1997-02-16 or 2/16/1997, got {text!r}")
    y, m, d = int(year), int(month), int(day)
    if not (1900 <= y <= datetime.date.today().year and 1 <= m <= 12 and 1 <= d <= 31):
        raise ValueError(f"db is out of range (year 1900-now, month 01-12, day 01-31): {text!r}")
    return f"{y:04d}{m:02d}{d:02d}"


def normalize_field(key: str, value: str) -> str:
    """Normalize a non-email, non-phone user_data field before hashing.

    Rules follow Meta's Customer Information Parameters page; see docs/meta-rules.md.
    Raises ValueError when a value cannot be normalized without guessing.
    """
    text = unicodedata.normalize("NFKC", value).strip().lower()
    if key in ("fn", "ln", "ct", "st"):
        return _letters_only(text)
    if key == "country":
        code = _letters_only(text)
        if len(code) != 2:
            raise ValueError(f"country must be a 2-letter ISO 3166-1 alpha-2 code such as 'us', got {value!r}")
        return code
    if key == "zp":
        compact = re.sub(r"[\s\-]", "", text)
        return compact[:5] if compact[:5].isdigit() else compact
    if key == "ge":
        if text[:1] not in ("f", "m"):
            raise ValueError(f"ge must start with 'f' or 'm', got {value!r}")
        return text[:1]
    if key == "db":
        return _normalize_dob(text)
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
