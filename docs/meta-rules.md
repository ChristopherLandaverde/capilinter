# Rules traced to Meta's documentation

`Rule record / v0.2.0` · Checked Nov 17, 2026 · Sources fetched on that date; Meta can change them.

Sources:
- **[CIP]** Customer Information Parameters ↗ https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/customer-information-parameters
- **[SEP]** Server Event Parameters ↗ https://developers.facebook.com/docs/marketing-api/conversions-api/parameters/server-event
- **[DQ]** Dataset Quality API ↗ https://developers.facebook.com/docs/marketing-api/conversions-api/dataset-quality-api
- **[VER]** Verifying your setup ↗ https://developers.facebook.com/documentation/ads-commerce/conversions-api/verifying-setup

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

| Key | Meta rule (paraphrased) | `capilinter hash` | Doc example → output | Status |
|---|---|---|---|---|
| `em` | trim, lowercase | same | `John_Smith@gmail.com` → `john_smith@gmail.com` | ✓ |
| `ph` | remove symbols, letters, leading zeros; include country code | same; also `00`/`(0)` prefixes, extensions, Unicode digits. National numbers get `--country-code` (default `1`, 10-digit only); a national `0…` number under the default is refused rather than guessed | `(650)555-1212` → `16505551212` | + v0.1 turned UK `07911 123456` into a `+1` number. |
| `fn`, `ln` | lowercase, no punctuation; UTF-8 letters allowed | lowercase, letters and combining marks only (keeps `é`, `जॉन`) | `Valéry` → `valéry` | ✓ |
| `ct` | lowercase, no punctuation, special characters or spaces; UTF-8 allowed | lowercase, letters only | `New York` → `newyork` | + v0.1 stripped non-ASCII letters (`São Paulo` → `sopaulo`). |
| `st` | US: 2-letter code; non-US: lowercase, no punctuation or spaces | lowercase, letters only | `AZ` → `az` | + v0.1 cut every value to 2 characters, breaking non-US states. |
| `zp` | lowercase, no spaces or dashes; US first 5 digits | same | `M1 1AE` → `m11ae`, `94035-1234` → `94035` | ✓ |
| `country` | lowercase ISO 3166-1 alpha-2 | lowercase; anything not 2 letters is refused (exit 2) | `United States` → `us` per doc; the tool refuses it, since mapping names to codes is out of scope | + v0.1 produced `un`. |
| `ge` | single lowercase initial `f` / `m` | accepts `f m female male`; anything else refused | `Female` → `f` | + v0.1 passed other values through. |
| `db` | `YYYYMMDD`; year 1900–now, month 01–12, day 01–31 | parses `YYYY-MM-DD`, `YYYYMMDD`, `M/D/YYYY` (US order, as in Meta's example), `D/M/YYYY` when day > 12; refuses dates that do not exist (`02/30`) or fall outside 1900–now | `2/16/1997` → `19970216` | + v0.1 kept digit order (`02161997`). |
| `fbc` | `fb.<subdomain_index>.<creation_time>.<fbclid>`, not hashed | 13-digit millisecond `creation_time` required; else `MALFORMED_FBC` WARNING, no score credit | `fb.1.1554763741205.AbC…` | ✓ |
| `fbp` | `fb.<subdomain_index>.<creation_time>.<random>`, not hashed | 13-digit millisecond `creation_time` required; else `MALFORMED_FBP` WARNING, no score credit | `fb.1.1596403881668.1116446470` | ✓ |
| `client_ip_address`, `client_user_agent` | not hashed | sent as captured | — | ✓ |

## Live: Dataset Quality API (L3, fixture-verified)

`capilinter live quality` and the `read_dataset_quality` MCP tool call `GET https://graph.facebook.com/v25.0/dataset_quality` for website events, read-only, and report Meta's own numbers. Tested only against synthetic responses in `fixtures/live/`, shaped after the samples on the DQ page.

| Rule | Code | Severity | Source | Status |
|---|---|---|---|---|
| Event Match Quality of 6.0 or higher is recommended | `LIVE_EMQ_BELOW_RECOMMENDED` | WARNING | VER | ✓ |
| Meta's EMQ diagnostics (name, share of events affected, Meta's solution) passed through | `LIVE_EMQ_DIAGNOSTIC` | WARNING | DQ | ✓ |
| Event coverage below Meta's `goal_percentage` | `LIVE_EVENT_COVERAGE_BELOW_GOAL` | WARNING | DQ | ✓ |
| Server events carrying the `event_id` dedup key below 100% | `LIVE_SERVER_DEDUP_KEY_LOW` | WARNING | DQ | □ Meta reports the share; it does not state a threshold. Anything under 100% means some server events cannot be deduplicated, so it is flagged. |

## Known limits

- Ambiguous dates such as `03/04/1997` are read month-first (US), following Meta's own example. Send `YYYY-MM-DD` to avoid guessing.
- US state names (`California`) normalize to `california`, not `ca`: the tool does not map names to codes. Send the 2-letter code.
- "At least one user_data parameter" follows Meta's literal rule, so an event with only `client_ip_address` passes. Its estimated match quality will be POOR.
- Live mode has not been run against a real dataset. It sends the token in an `Authorization: Bearer` header rather than the `access_token` query parameter Meta's examples use, to keep the token out of URLs; that header form is not yet verified against Meta's API.
- Match-quality scoring is a heuristic. Meta does not publish its Event Match Quality formula.
