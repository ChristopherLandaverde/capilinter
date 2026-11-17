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
    - A '+' or '00' prefix means the number already carries its country code.
    - Otherwise the number is national: a leading trunk '0' is dropped and
      default_country_code is prepended. With the default code '1' (US/Canada)
      only 10-digit numbers get it, and a leading '0' raises ValueError,
      because no US number starts with 0 and guessing the country would
      produce a hash that never matches.
    """
    raw = _EXTENSION.sub("", unicodedata.normalize("NFKC", phone).strip())
    raw = raw.replace("(0)", "")  # national trunk prefix, e.g. +44 (0)20
    international = raw.startswith("+") or raw.startswith("00")
    digits = re.sub(r"[^0-9]", "", raw)
    if international:
        return digits.lstrip("0")
    national = digits.lstrip("0")
    if default_country_code == "1":
        if national != digits:
            raise ValueError(
                f"{phone!r} starts with a national trunk 0, so it is not a US number. "
                "Pass its country code (e.g. --country-code 44) or write it with '+'."
            )
        return "1" + national if len(national) == 10 else national
    return default_country_code + national if default_country_code else national


def _letters_only(text: str) -> str:
    """Letters only, keeping UTF-8 letters and their combining marks ('é', 'जॉन'); no digits, punctuation or spaces."""
    return "".join(ch for ch in text if ch.isalpha() or unicodedata.category(ch).startswith("M"))


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
    try:
        date = datetime.date(int(year), int(month), int(day))
    except ValueError:
        raise ValueError(f"db is not a real calendar date: {text!r}") from None
    if not 1900 <= date.year <= datetime.date.today().year:
        raise ValueError(f"db year must be between 1900 and this year: {text!r}")
    return date.strftime("%Y%m%d")


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
        genders = {"f": "f", "female": "f", "m": "m", "male": "m"}
        if text not in genders:
            raise ValueError(f"ge must be f, m, female or male, got {value!r}")
        return genders[text]
    if key == "db":
        return _normalize_dob(text)
    raise ValueError(f"Unsupported field: {key}")


def normalize_and_hash_email(email: str) -> str:
    return _sha256(normalize_email(email))


def normalize_and_hash_phone(phone: str, default_country_code: str = "1") -> str:
    return _sha256(normalize_phone(phone, default_country_code))


def normalize_value(key: str, value: str, default_country_code: str = "1") -> str:
    """Normalize any hashed user_data field the way Meta documents. Raises ValueError if it cannot."""
    if key == "em":
        return normalize_email(value)
    if key == "ph":
        return normalize_phone(value, default_country_code)
    return normalize_field(key, value)


def normalize_and_hash_field(key: str, value: str, default_country_code: str = "1") -> str:
    return _sha256(normalize_value(key, value, default_country_code))
