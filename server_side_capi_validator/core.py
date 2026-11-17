"""Schema, hashing, and deduplication checks for a single CAPI event."""

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SHA256_LOWER = re.compile(r"^[a-f0-9]{64}$")
SHA256_ANYCASE = re.compile(r"^[a-fA-F0-9]{64}$")

# Meta rejects events older than 7 days for most action sources.
MAX_EVENT_AGE_SECONDS = 7 * 24 * 60 * 60
# Allow small clock skew before flagging future timestamps.
FUTURE_SKEW_SECONDS = 5 * 60

VALID_ACTION_SOURCES = {
    "website", "app", "phone_call", "chat", "email",
    "physical_store", "system_generated", "business_messaging", "other",
}

# user_data keys Meta expects hashed (SHA-256, lowercase hex).
HASHED_KEYS = ("em", "ph", "fn", "ln", "ge", "db", "ct", "st", "zp", "country")


@dataclass
class ValidationIssue:
    severity: str  # "ERROR" or "WARNING"
    code: str
    message: str
    field: str


@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]


def is_sha256(val: Any) -> bool:
    """True only for a 64-char lowercase hex string (the form Meta expects)."""
    return isinstance(val, str) and bool(SHA256_LOWER.match(val))


def _as_list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _check_hashed_field(key: str, value: Any, issues: List[ValidationIssue]) -> None:
    path = f"user_data.{key}"
    text = str(value)
    if is_sha256(text):
        return
    if SHA256_ANYCASE.match(text):
        issues.append(ValidationIssue(
            "WARNING", "HASH_NOT_LOWERCASE",
            f"'{key}' looks like SHA-256 but uses uppercase hex. Send lowercase hex.", path))
        return
    if key == "em" and "@" in text:
        issues.append(ValidationIssue(
            "ERROR", "RAW_PII_UNHASHED_EMAIL",
            "Found a raw email address. Normalize (trim, lowercase) and SHA-256 hash it.", path))
        return
    if key == "ph" and re.fullmatch(r"[\d\s()+\-.]{7,}", text):
        issues.append(ValidationIssue(
            "ERROR", "RAW_PII_UNHASHED_PHONE",
            "Found a raw phone number. Normalize to digits with country code (no '+') and SHA-256 hash it.", path))
        return
    issues.append(ValidationIssue(
        "ERROR", "INVALID_SHA256",
        f"'{key}' is not a 64-character lowercase SHA-256 hex string.", path))


def validate_capi_payload(event: Dict[str, Any], now: Optional[int] = None) -> ValidationResult:
    """Validate one CAPI event. `now` (Unix seconds) is injectable for tests."""
    issues: List[ValidationIssue] = []
    if not isinstance(event, dict):
        issues.append(ValidationIssue("ERROR", "INVALID_EVENT", "Event must be a JSON object.", "$"))
        return ValidationResult(is_valid=False, issues=issues)

    now = int(time.time()) if now is None else now

    # 1. Root attributes
    if not event.get("event_name"):
        issues.append(ValidationIssue("ERROR", "MISSING_EVENT_NAME", "Event is missing 'event_name'.", "event_name"))

    event_time = event.get("event_time")
    if event_time is None:
        issues.append(ValidationIssue("ERROR", "MISSING_EVENT_TIME", "Event is missing 'event_time' (Unix seconds).", "event_time"))
    elif isinstance(event_time, bool) or not isinstance(event_time, (int, float)):
        issues.append(ValidationIssue("ERROR", "INVALID_EVENT_TIME_TYPE", "'event_time' must be a Unix timestamp in seconds.", "event_time"))
    else:
        if event_time > 10_000_000_000:
            issues.append(ValidationIssue("ERROR", "EVENT_TIME_IN_MILLISECONDS", "'event_time' looks like milliseconds. Send seconds.", "event_time"))
        elif event_time > now + FUTURE_SKEW_SECONDS:
            issues.append(ValidationIssue("ERROR", "EVENT_TIME_IN_FUTURE", "'event_time' is in the future.", "event_time"))
        elif now - event_time > MAX_EVENT_AGE_SECONDS:
            issues.append(ValidationIssue("WARNING", "EVENT_TIME_STALE", "'event_time' is older than 7 days; Meta may reject it.", "event_time"))

    # 2. Deduplication key
    if not event.get("event_id"):
        issues.append(ValidationIssue(
            "ERROR", "MISSING_EVENT_ID",
            "Missing 'event_id'. Browser-to-server deduplication needs the same event_id + event_name on pixel and server events.",
            "event_id"))

    # 3. Action source
    action_source = event.get("action_source")
    if not action_source:
        issues.append(ValidationIssue("ERROR", "MISSING_ACTION_SOURCE", "'action_source' is required (e.g. 'website').", "action_source"))
    elif action_source not in VALID_ACTION_SOURCES:
        issues.append(ValidationIssue("WARNING", "UNUSUAL_ACTION_SOURCE", f"'{action_source}' is not a standard action_source.", "action_source"))

    # 4. user_data
    user_data = event.get("user_data", {})
    if not isinstance(user_data, dict):
        issues.append(ValidationIssue("ERROR", "INVALID_USER_DATA", "'user_data' must be a JSON object.", "user_data"))
        user_data = {}

    for key in HASHED_KEYS:
        for value in _as_list(user_data.get(key)):
            _check_hashed_field(key, value, issues)

    if action_source == "website":
        if not user_data.get("client_user_agent"):
            issues.append(ValidationIssue(
                "ERROR", "MISSING_CLIENT_USER_AGENT",
                "Website events require 'user_data.client_user_agent'.", "user_data.client_user_agent"))
        if not event.get("event_source_url"):
            issues.append(ValidationIssue(
                "WARNING", "MISSING_EVENT_SOURCE_URL",
                "Website events should include 'event_source_url'.", "event_source_url"))

    fbc = user_data.get("fbc")
    if fbc and not str(fbc).startswith("fb."):
        issues.append(ValidationIssue("WARNING", "MALFORMED_FBC", "'fbc' should look like fb.1.<timestamp>.<fbclid>. Do not hash it.", "user_data.fbc"))
    fbp = user_data.get("fbp")
    if fbp and not str(fbp).startswith("fb."):
        issues.append(ValidationIssue("WARNING", "MALFORMED_FBP", "'fbp' should look like fb.1.<timestamp>.<random>. Do not hash it.", "user_data.fbp"))

    if not any(user_data.get(k) for k in ("em", "ph", "external_id", "fbp", "fbc", "client_ip_address")):
        issues.append(ValidationIssue(
            "ERROR", "NO_CUSTOMER_INFORMATION",
            "user_data has no matchable customer information (em, ph, external_id, fbp, fbc, client_ip_address).",
            "user_data"))

    is_valid = not any(i.severity == "ERROR" for i in issues)
    return ValidationResult(is_valid=is_valid, issues=issues)
