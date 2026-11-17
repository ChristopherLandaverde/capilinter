"""Schema, hashing, and deduplication checks for a single CAPI event.

Each rule is traced to Meta's Server Event and Customer Information Parameters
docs in docs/meta-rules.md.
"""

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

SHA256_LOWER = re.compile(r"^[a-f0-9]{64}$")
SHA256_ANYCASE = re.compile(r"^[a-fA-F0-9]{64}$")

# Meta rejects events older than 7 days for most action sources.
MAX_EVENT_AGE_SECONDS = 7 * 24 * 60 * 60
# Allow small clock skew before flagging future timestamps.
FUTURE_SKEW_SECONDS = 5 * 60

VALID_ACTION_SOURCES = {
    "website",
    "app",
    "phone_call",
    "chat",
    "email",
    "physical_store",
    "system_generated",
    "business_messaging",
    "other",
}

# user_data keys Meta expects hashed (SHA-256, lowercase hex).
HASHED_KEYS = ("em", "ph", "fn", "ln", "ge", "db", "ct", "st", "zp", "country")

# fb.<subdomain index 0-2>.<creation time in ms>.<fbclid or random number>
FB_COOKIE = re.compile(r"^fb\.[0-2]\.\d{13}\.\S+$")


@dataclass
class ValidationIssue:
    severity: str  # "ERROR" or "WARNING"
    code: str
    message: str
    field: str


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]


def is_sha256(val: Any) -> bool:
    """True only for a 64-char lowercase hex string (the form Meta expects)."""
    return isinstance(val, str) and bool(SHA256_LOWER.match(val))


def is_fb_cookie(val: Any) -> bool:
    """True for an fbc/fbp value in Meta's fb.<0-2>.<ms timestamp>.<id> form."""
    return isinstance(val, str) and bool(FB_COOKIE.match(val))


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _check_hashed_field(key: str, value: Any, issues: list[ValidationIssue]) -> None:
    path = f"user_data.{key}"
    text = str(value)
    if is_sha256(text):
        return
    if SHA256_ANYCASE.match(text):
        issues.append(
            ValidationIssue(
                "WARNING",
                "HASH_NOT_LOWERCASE",
                f"'{key}' looks like SHA-256 but uses uppercase hex. Send lowercase hex.",
                path,
            )
        )
        return
    if key == "em" and "@" in text:
        issues.append(
            ValidationIssue(
                "ERROR",
                "RAW_PII_UNHASHED_EMAIL",
                "Found a raw email address. Normalize (trim, lowercase) and SHA-256 hash it.",
                path,
            )
        )
        return
    if key == "ph" and re.fullmatch(r"[\d\s()+\-.]{7,}", text):
        issues.append(
            ValidationIssue(
                "ERROR",
                "RAW_PII_UNHASHED_PHONE",
                "Found a raw phone number. Normalize to digits with country code (no '+') and SHA-256 hash it.",
                path,
            )
        )
        return
    issues.append(
        ValidationIssue(
            "ERROR",
            "INVALID_SHA256",
            f"'{key}' is not a 64-character lowercase SHA-256 hex string. "
            f"Normalize it and hash it (capi-validator hash --field {key} VALUE).",
            path,
        )
    )


def validate_capi_payload(event: dict[str, Any], now: int | None = None) -> ValidationResult:
    """Validate one CAPI event. `now` (Unix seconds) is injectable for tests."""
    issues: list[ValidationIssue] = []
    if not isinstance(event, dict):
        issues.append(ValidationIssue("ERROR", "INVALID_EVENT", "Event must be a JSON object.", "$"))
        return ValidationResult(is_valid=False, issues=issues)

    now = int(time.time()) if now is None else now

    # 1. Root attributes
    if not event.get("event_name"):
        issues.append(ValidationIssue("ERROR", "MISSING_EVENT_NAME", "Event is missing 'event_name'.", "event_name"))

    event_time = event.get("event_time")
    if event_time is None:
        issues.append(
            ValidationIssue(
                "ERROR", "MISSING_EVENT_TIME", "Event is missing 'event_time' (Unix seconds).", "event_time"
            )
        )
    elif isinstance(event_time, bool) or not isinstance(event_time, (int, float)):
        issues.append(
            ValidationIssue(
                "ERROR",
                "INVALID_EVENT_TIME_TYPE",
                "'event_time' must be a Unix timestamp in seconds (a number, not a string).",
                "event_time",
            )
        )
    elif not math.isfinite(event_time) or event_time <= 0:
        issues.append(
            ValidationIssue(
                "ERROR",
                "INVALID_EVENT_TIME_VALUE",
                "'event_time' must be a positive, finite Unix timestamp.",
                "event_time",
            )
        )
    else:
        if event_time > 10_000_000_000:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "EVENT_TIME_IN_MILLISECONDS",
                    "'event_time' looks like milliseconds. Send seconds.",
                    "event_time",
                )
            )
        elif event_time > now + FUTURE_SKEW_SECONDS:
            issues.append(
                ValidationIssue("ERROR", "EVENT_TIME_IN_FUTURE", "'event_time' is in the future.", "event_time")
            )
        elif now - event_time > MAX_EVENT_AGE_SECONDS:
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "EVENT_TIME_STALE",
                    "'event_time' is older than 7 days. Meta rejects the whole request if any event in it is this old.",
                    "event_time",
                )
            )

    # 2. Deduplication key
    event_id = event.get("event_id")
    if event_id is None or event_id == "":
        issues.append(
            ValidationIssue(
                "ERROR",
                "MISSING_EVENT_ID",
                "Missing 'event_id'. Browser-to-server deduplication needs the same event_id + event_name on pixel and server events.",
                "event_id",
            )
        )

    # 3. Action source
    action_source = event.get("action_source")
    if action_source is None or action_source == "":
        issues.append(
            ValidationIssue(
                "ERROR", "MISSING_ACTION_SOURCE", "'action_source' is required (e.g. 'website').", "action_source"
            )
        )
    elif not isinstance(action_source, str) or action_source not in VALID_ACTION_SOURCES:
        issues.append(
            ValidationIssue(
                "ERROR",
                "INVALID_ACTION_SOURCE",
                f"{action_source!r} is not a valid action_source ({', '.join(sorted(VALID_ACTION_SOURCES))}).",
                "action_source",
            )
        )

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
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "MISSING_CLIENT_USER_AGENT",
                    "Website events require 'user_data.client_user_agent'.",
                    "user_data.client_user_agent",
                )
            )
        if not event.get("event_source_url"):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "MISSING_EVENT_SOURCE_URL",
                    "Website events require 'event_source_url'.",
                    "event_source_url",
                )
            )

    for key, tail in (("fbc", "fbclid"), ("fbp", "random number")):
        value = user_data.get(key)
        if value and not is_fb_cookie(value):
            issues.append(
                ValidationIssue(
                    "WARNING",
                    f"MALFORMED_{key.upper()}",
                    f"'{key}' should look like fb.1.<ms timestamp>.<{tail}>. Do not hash it.",
                    f"user_data.{key}",
                )
            )

    # Meta: "You must include at least one user_data parameter."
    if not any(v not in (None, "", []) for v in user_data.values()):
        issues.append(
            ValidationIssue(
                "ERROR",
                "NO_CUSTOMER_INFORMATION",
                "user_data is empty. Meta requires at least one correctly formatted user_data parameter.",
                "user_data",
            )
        )

    is_valid = not any(i.severity == "ERROR" for i in issues)
    return ValidationResult(is_valid=is_valid, issues=issues)


def find_duplicate_event_ids(events: list[Any]) -> list[ValidationIssue]:
    """Flag (event_name, event_id) pairs that repeat inside one batch.

    Meta deduplicates on that pair, so a repeat inside one request drops
    real conversions.
    """
    seen: dict[Any, int] = {}
    issues: list[ValidationIssue] = []
    for idx, event in enumerate(events, 1):
        if not isinstance(event, dict) or event.get("event_id") in (None, ""):
            continue
        key = (str(event.get("event_name")), str(event.get("event_id")))
        if key in seen:
            issues.append(
                ValidationIssue(
                    "WARNING",
                    "DUPLICATE_EVENT_ID",
                    f"Event {idx} repeats event_name/event_id {key} from event {seen[key]}; Meta will deduplicate one of them.",
                    f"data[{idx - 1}].event_id",
                )
            )
        else:
            seen[key] = idx
    return issues
