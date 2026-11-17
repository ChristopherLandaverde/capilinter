# server-side-capi-validator

Checks Meta Conversions API payloads for the handoff errors that break matching and deduplication, before they reach Events Manager.

`Tool / v0.1.0` · Python 3.10+ · zero dependencies · runs offline

## Scope

**Does:** validate CAPI event JSON (single events, arrays, or `{"data": [...]}` request bodies) from webhooks, sGTM logs, or fixtures. Checks schema, PII hashing, dedup keys, and timestamps. Prints an estimated match-quality score.

**Does not:** call the Graph API, read cookies, or reproduce Meta's Event Match Quality formula. Meta does not publish that formula; the score here is a weighted heuristic for comparing payloads, not a prediction of the Events Manager number.

## The trace

```
□ OBSERVED   — event_name, event_time, event_id, action_source, event_source_url, user_data
× BROKEN     — raw email or phone in user_data, unhashed or malformed hashes on any
               PII key, missing event_id (pixel/server dedup fails), repeated
               event_name/event_id pairs in one batch, event_time in ms, in the
               future, non-numeric or NaN, unknown action_source, website events
               without client_user_agent or event_source_url, malformed fbc/fbp
+ REPAIRED   — `capi-validator hash --field <key>` outputs the normalized SHA-256 value to send
✓ VERIFIED   — exit code 0 only when every event passes; --strict fails on warnings too
```

## Install

```bash
git clone https://github.com/ChristopherLandaverde/server-side-capi-validator.git
cd server-side-capi-validator
pip install .
```

## Use

```bash
capi-validator inspect fixtures/valid_payload.json
capi-validator inspect payload.json --strict     # warnings fail the run
capi-validator inspect payload.json --json       # machine-readable report for CI
capi-validator hash "  Jane.Doe@Example.com "     # → sha256 of jane.doe@example.com
capi-validator hash "(555) 010-2834" --phone      # → sha256 of 15550102834
capi-validator hash "San Francisco" --field ct     # → sha256 of sanfrancisco
```

Sample output:

```
[1/1] Lead  event_id=demo_lead_2
  × ERROR     RAW_PII_UNHASHED_EMAIL: Found a raw email address. Normalize (trim, lowercase) and SHA-256 hash it.
  Estimated match quality: 1.0/10.0 (POOR)
  Matched: Client IP address, Client user agent
  + Add a SHA-256 hashed, normalized email (+3.0).
```

Exit codes: `0` pass, `1` validation failure or no events, `2` unreadable file, invalid JSON, or a payload that is not CAPI-shaped.

Errors fail the run. Warnings (stale `event_time`, uppercase hashes, malformed `fbc`/`fbp`, duplicate event IDs in a batch) pass unless `--strict` is set. Staleness is a warning because the check uses the clock at audit time: when you replay last month's sGTM logs, every event is "old". Use `--strict` on payloads you are about to send.

## Normalization rules

| Field | Normalize | Then |
|---|---|---|
| `em` | trim, lowercase | SHA-256, lowercase hex |
| `ph` | digits only, country code, no `+`, `00`, `(0)` or leading zeros; extensions dropped; 10-digit numbers get `1` by default | SHA-256, lowercase hex |
| `fn`, `ln` | lowercase, letters only | SHA-256, lowercase hex |
| `ct` | lowercase, a–z only, no spaces | SHA-256, lowercase hex |
| `st`, `country` | lowercase 2-letter code | SHA-256, lowercase hex |
| `zp` | lowercase, no spaces or dashes; US ZIP+4 trimmed to 5 digits | SHA-256, lowercase hex |
| `ge` | `f` or `m` | SHA-256, lowercase hex |
| `db` | `YYYYMMDD` (digits only; input must already be in year-month-day order) | SHA-256, lowercase hex |
| `fbc`, `fbp`, `client_ip_address`, `client_user_agent` | send as captured | do not hash |

## Estimated match-quality weights

| Parameter | Weight |
|---|---|
| Hashed email (`em`) | 3.0 |
| Hashed phone (`ph`) | 2.5 |
| Click ID (`fbc`) | 1.5 |
| Browser ID (`fbp`) | 1.0 |
| `external_id` | 1.0 |
| `client_ip_address` | 0.5 |
| `client_user_agent` | 0.5 |

Hashed fields earn credit only when the value is a valid lowercase SHA-256; `fbc` and `fbp` only when they match `fb.<0-2>.<timestamp>.<id>`. Grades: EXCELLENT ≥ 8.5, GOOD ≥ 7.0, FAIR ≥ 5.0.

## Fixtures

`fixtures/` holds synthetic payloads (no client data): `valid_payload.json`, `unhashed_pii.json`, `unhashed_phone.json`, `missing_event_id.json`. Fixture timestamps are fixed in the past, so they pass in default mode and trip `EVENT_TIME_STALE` under `--strict`. Tests pass a fixed clock, so results do not depend on the day they run.

## Test

```bash
python -m unittest discover -s tests -v
```

CI runs the suite and a CLI smoke test on Python 3.10–3.14.

---

Built by Christopher Landaverde, FOCO Systems. Field notes on server-side tracking ↗ [focosys.io](https://focosys.io) · christopher@focosys.io

MIT License.
