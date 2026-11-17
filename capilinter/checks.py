"""Check registry: the single source of truth for every issue code.

Each check carries its severity, what it is about, why it matters, how to fix it,
and the Meta documentation page it comes from. The validator, the CLI (`checks`,
`explain`), the JSON report and the MCP server all read from here.
Every code is also traced in docs/meta-rules.md; a test keeps the two in step.
"""

from dataclasses import asdict, dataclass

ERROR = "ERROR"
WARNING = "WARNING"

SEP = "https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/server-event"
CIP = "https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/customer-information-parameters"
DEDUP = "https://developers.facebook.com/docs/marketing-api/conversions-api/deduplicate-pixel-and-server-events"
DQ = "https://developers.facebook.com/docs/marketing-api/conversions-api/dataset-quality-api"
VERIFY = "https://developers.facebook.com/documentation/ads-commerce/conversions-api/verifying-setup"

AREAS = ("required", "timestamps", "dedup", "hashing", "browser_ids", "live")


@dataclass(frozen=True)
class Check:
    code: str
    severity: str
    area: str
    title: str
    why: str
    fix: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


_ALL = (
    # Required fields
    Check(
        "INVALID_EVENT",
        ERROR,
        "required",
        "Event is not a JSON object",
        "Meta expects each item in `data` to be an event object; anything else is rejected.",
        "Send each event as a JSON object with event_name, event_time, action_source and user_data.",
        SEP,
    ),
    Check(
        "MISSING_EVENT_NAME",
        ERROR,
        "required",
        "Missing event_name",
        "event_name is required, and Meta deduplicates on event_name together with event_id.",
        "Set event_name to the same standard or custom name the pixel uses for this event.",
        SEP,
    ),
    Check(
        "MISSING_ACTION_SOURCE",
        ERROR,
        "required",
        "Missing action_source",
        "action_source is required; Meta uses it to know where the conversion happened.",
        "Set action_source, for example 'website' for events that also fire the pixel.",
        SEP,
    ),
    Check(
        "INVALID_ACTION_SOURCE",
        ERROR,
        "required",
        "Unknown action_source",
        "Meta accepts only its documented action_source values; others are rejected.",
        "Use one of: email, website, app, phone_call, chat, physical_store, system_generated, business_messaging, other.",
        SEP,
    ),
    Check(
        "INVALID_USER_DATA",
        ERROR,
        "required",
        "user_data is not an object",
        "user_data is required and must be a map of customer information parameters.",
        "Send user_data as a JSON object of customer information parameters.",
        SEP,
    ),
    Check(
        "NO_CUSTOMER_INFORMATION",
        ERROR,
        "required",
        "user_data is empty",
        "Meta requires at least one correctly formatted user_data parameter; without one the event cannot be matched.",
        "Add customer information: hashed em or ph, external_id, fbp, fbc, client_ip_address or client_user_agent.",
        CIP,
    ),
    Check(
        "MISSING_CLIENT_USER_AGENT",
        ERROR,
        "required",
        "Website event without client_user_agent",
        "Meta requires client_user_agent for website events sent through the Conversions API.",
        "Forward the browser's user agent from your server or sGTM container as user_data.client_user_agent.",
        CIP,
    ),
    Check(
        "MISSING_EVENT_SOURCE_URL",
        ERROR,
        "required",
        "Website event without event_source_url",
        "Meta requires event_source_url for website events, and it should match the verified domain.",
        "Send the page URL where the event happened as event_source_url.",
        SEP,
    ),
    # Timestamps
    Check(
        "MISSING_EVENT_TIME",
        ERROR,
        "timestamps",
        "Missing event_time",
        "event_time is required: a Unix timestamp in seconds for when the event happened.",
        "Set event_time to the Unix time in seconds (GMT) when the action occurred.",
        SEP,
    ),
    Check(
        "INVALID_EVENT_TIME_TYPE",
        ERROR,
        "timestamps",
        "event_time is not a number",
        "event_time must be a Unix timestamp in seconds; a string or boolean is not one.",
        "Send event_time as a number, not a quoted string.",
        SEP,
    ),
    Check(
        "INVALID_EVENT_TIME_VALUE",
        ERROR,
        "timestamps",
        "event_time is not a valid timestamp",
        "NaN, infinity, zero and negative values are not points in time Meta can attribute.",
        "Send the positive Unix time in seconds when the action occurred.",
        SEP,
    ),
    Check(
        "EVENT_TIME_IN_MILLISECONDS",
        ERROR,
        "timestamps",
        "event_time is in milliseconds",
        "Meta expects seconds; a millisecond value reads as a date far in the future.",
        "Divide by 1000, or use the server's seconds clock.",
        SEP,
    ),
    Check(
        "EVENT_TIME_IN_FUTURE",
        ERROR,
        "timestamps",
        "event_time is in the future",
        "An event cannot happen after it is sent; Meta rejects future timestamps.",
        "Use the time the action occurred, and check the server clock and time zone handling.",
        SEP,
    ),
    Check(
        "EVENT_TIME_STALE",
        WARNING,
        "timestamps",
        "event_time is older than 7 days",
        "Meta accepts events up to 7 days old; if any event in a request is older, the whole request fails.",
        "Send events as close to real time as possible, and drop or split out events older than 7 days.",
        SEP,
    ),
    # Deduplication
    Check(
        "MISSING_EVENT_ID",
        ERROR,
        "dedup",
        "Missing event_id",
        "Without event_id, Meta cannot deduplicate the server event against the browser pixel event, so conversions double count.",
        "Generate one event_id per action and send the same value from the pixel (eventID) and the server (event_id).",
        DEDUP,
    ),
    Check(
        "DUPLICATE_EVENT_ID",
        WARNING,
        "dedup",
        "event_name + event_id repeated in one batch",
        "Meta deduplicates on event_name + event_id, so a repeat inside one request drops a real conversion.",
        "Give each distinct action its own event_id; reuse an event_id only between the pixel and the server copy of the same action.",
        DEDUP,
    ),
    # Hashing
    Check(
        "RAW_PII_UNHASHED_EMAIL",
        ERROR,
        "hashing",
        "Raw email in user_data",
        "Meta requires em to be normalized and SHA-256 hashed; sending it raw exposes PII and hurts matching.",
        "Trim and lowercase the email, hash it with SHA-256 (capilinter hash), and send the lowercase hex digest.",
        CIP,
    ),
    Check(
        "RAW_PII_UNHASHED_PHONE",
        ERROR,
        "hashing",
        "Raw phone number in user_data",
        "Meta requires ph to be normalized and SHA-256 hashed; sending it raw exposes PII and hurts matching.",
        "Keep digits only with the country code (no '+' or leading zeros), hash with SHA-256 (capilinter hash --phone).",
        CIP,
    ),
    Check(
        "INVALID_SHA256",
        ERROR,
        "hashing",
        "Customer field is not a SHA-256 hash",
        "Meta requires em, ph, fn, ln, ct, st, zp, country, ge and db to be hashed; anything else will not match.",
        "Normalize the value as Meta documents and hash it (capilinter hash --field <key> VALUE).",
        CIP,
    ),
    Check(
        "HASH_NOT_LOWERCASE",
        WARNING,
        "hashing",
        "Hash uses uppercase hex",
        "Meta's examples are lowercase hex digests; uppercase can fail to match.",
        "Send the SHA-256 digest as lowercase hex.",
        CIP,
    ),
    # Browser IDs
    Check(
        "MALFORMED_FBC",
        WARNING,
        "browser_ids",
        "fbc is not in Meta's format",
        "fbc should be fb.<subdomain_index>.<creation_time in ms>.<fbclid>, unhashed; a malformed click ID cannot attribute the click.",
        "Pass the _fbc cookie as is, or build it from fbclid on the landing URL with a millisecond timestamp. Do not hash it.",
        CIP,
    ),
    Check(
        "MALFORMED_FBP",
        WARNING,
        "browser_ids",
        "fbp is not in Meta's format",
        "fbp should be fb.<subdomain_index>.<creation_time in ms>.<random>, unhashed; a malformed browser ID cannot match.",
        "Pass the _fbp first-party cookie as is. Do not hash it.",
        CIP,
    ),
    # Live (Dataset Quality API)
    Check(
        "LIVE_EMQ_BELOW_RECOMMENDED",
        WARNING,
        "live",
        "Event Match Quality below 6.0",
        "Meta recommends an Event Match Quality of 6.0 or higher; lower scores mean fewer events match a Meta account.",
        "Send more customer information on the server event (hashed em and ph, fbc, fbp, external_id) and work through Meta's diagnostics.",
        VERIFY,
    ),
    Check(
        "LIVE_EMQ_DIAGNOSTIC",
        WARNING,
        "live",
        "Meta reports an Event Match Quality diagnostic",
        "Meta's Dataset Quality API lists diagnostics for problems it sees in the events it received.",
        "Follow the solution Meta gives in the diagnostic, then re-check the payload with capilinter inspect.",
        DQ,
    ),
    Check(
        "LIVE_EVENT_COVERAGE_BELOW_GOAL",
        WARNING,
        "live",
        "Event coverage below Meta's goal",
        "Meta compares server events with browser events; coverage under its goal means server events are missing.",
        "Send a server event for every browser event of this name, with the same event_name and event_id.",
        DQ,
    ),
    Check(
        "LIVE_SERVER_DEDUP_KEY_LOW",
        WARNING,
        "live",
        "Server events missing the dedup key",
        "Meta reports what share of server events carry the dedup key; events without it cannot be deduplicated against the pixel.",
        "Send event_id on every server event, matching the pixel's eventID.",
        DQ,
    ),
)

CHECKS: dict[str, Check] = {c.code: c for c in _ALL}


def get(code: str) -> Check:
    """Return the check for a code. Raises KeyError for an unregistered code."""
    return CHECKS[code]
