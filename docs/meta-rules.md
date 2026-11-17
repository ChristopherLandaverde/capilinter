# Rules traced to Meta's documentation

`Rule record / v0.2.0` · Checked Nov 17, 2026 · Sources fetched on that date; Meta can change them.

Sources:
- **[CIP]** Customer Information Parameters ↗ https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/customer-information-parameters
- **[SEP]** Server Event Parameters ↗ https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/server-event

Status: `✓` matches the doc · `+` fixed in v0.2.0 to match the doc · `□` stricter than the doc, on purpose (reason given).

## Server event fields

| Rule | Code(s) | Severity | Source | Status |
|---|---|---|---|---|
| `event_name` required | `MISSING_EVENT_NAME` | ERROR | SEP | ✓ |
| `event_time` required, Unix seconds | `MISSING_EVENT_TIME`, `INVALID_EVENT_TIME_TYPE`, `INVALID_EVENT_TIME_VALUE`, `EVENT_TIME_IN_MILLISECONDS`, `EVENT_TIME_IN_FUTURE` | ERROR | SEP | ✓ |
| `event_time` at most 7 days old; one stale event fails the whole request | `EVENT_TIME_STALE` | WARNING (`--strict`: fail) | SEP | □ Warning because the check uses the clock at audit time; replayed historical logs would all fail. |
| `event_id` for browser/server deduplication | `MISSING_EVENT_ID` | ERROR | SEP (optional, recommended) | □ Meta accepts events without it, but deduplication fails. Dedup readiness is this tool's job, so it is an error. |
| Same `event_name` + `event_id` repeated in one batch | `DUPLICATE_EVENT_ID` | WARNING | SEP (dedup key) | ✓ |
| `action_source` required, one of `email website app phone_call chat physical_store system_generated business_messaging other` | `MISSING_ACTION_SOURCE`, `INVALID_ACTION_SOURCE` | ERROR | SEP | ✓ |
| `event_source_url` required for website events | `MISSING_EVENT_SOURCE_URL` | ERROR | SEP | ✓ |
| `user_data` required, at least one parameter | `INVALID_USER_DATA`, `NO_CUSTOMER_INFORMATION` | ERROR | SEP, CIP | + v0.1 required one of six specific keys; now any parameter counts. |
| `client_user_agent` required for website events | `MISSING_CLIENT_USER_AGENT` | ERROR | CIP | ✓ |

## Customer information normalization

Hashed keys must be SHA-256, lowercase hex. A raw value is an ERROR (`RAW_PII_UNHASHED_EMAIL`, `RAW_PII_UNHASHED_PHONE`, `INVALID_SHA256`); uppercase hex is a WARNING (`HASH_NOT_LOWERCASE`).

| Key | Meta rule (paraphrased) | `capi-validator hash` | Doc example → output | Status |
|---|---|---|---|---|
| `em` | trim, lowercase | same | `John_Smith@gmail.com` → `john_smith@gmail.com` | ✓ |
| `ph` | remove symbols, letters, leading zeros; include country code | same; also `00`/`(0)` prefixes, extensions, Unicode digits; 10-digit numbers get `1` | `(650)555-1212` → `16505551212` | ✓ |
| `fn`, `ln` | lowercase, no punctuation; UTF-8 letters allowed | lowercase, letters only (keeps `é`) | `Valéry` → `valéry` | ✓ |
| `ct` | lowercase, no punctuation, special characters or spaces; UTF-8 allowed | lowercase, letters only | `New York` → `newyork` | + v0.1 stripped non-ASCII letters (`São Paulo` → `sopaulo`). |
| `st` | US: 2-letter code; non-US: lowercase, no punctuation or spaces | lowercase, letters only | `AZ` → `az` | + v0.1 cut every value to 2 characters, breaking non-US states. |
| `zp` | lowercase, no spaces or dashes; US first 5 digits | same | `M1 1AE` → `m11ae`, `94035-1234` → `94035` | ✓ |
| `country` | lowercase ISO 3166-1 alpha-2 | lowercase; anything not 2 letters is refused (exit 2) | `United States` → `us` per doc; the tool refuses it, since mapping names to codes is out of scope | + v0.1 produced `un`. |
| `ge` | single lowercase initial `f` / `m` | same; anything else refused | `Female` → `f` | + v0.1 passed other values through. |
| `db` | `YYYYMMDD`; year 1900–now, month 01–12, day 01–31 | parses `YYYY-MM-DD`, `YYYYMMDD`, `M/D/YYYY` (US order, as in Meta's example), `D/M/YYYY` when day > 12; out-of-range refused | `2/16/1997` → `19970216` | + v0.1 kept digit order (`02161997`). |
| `fbc` | `fb.<subdomain_index>.<creation_time>.<fbclid>`, not hashed | `MALFORMED_FBC` WARNING, no score credit | `fb.1.1554763741205.AbC…` | ✓ |
| `fbp` | `fb.<subdomain_index>.<creation_time>.<random>`, not hashed | `MALFORMED_FBP` WARNING, no score credit | `fb.1.1596403881668.1116446470` | ✓ |
| `client_ip_address`, `client_user_agent` | not hashed | sent as captured | — | ✓ |

## Known limits

- Ambiguous dates such as `03/04/1997` are read month-first (US), following Meta's own example. Send `YYYY-MM-DD` to avoid guessing.
- Match-quality scoring is a heuristic. Meta does not publish its Event Match Quality formula.
