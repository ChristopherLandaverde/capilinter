# Decisions

`Build log / server-side-capi-validator` · Nov 2026 · Decisions made without separate approval, with reasons.

## v0.1.0 (initial release)

- **Zero dependencies, plain-text CLI.** The first plan called for "rich terminal tables"; dropped to keep `pip install .` offline-safe and CI-trivial.
- **Meta CAPI only.** The first plan mentioned LinkedIn; its Conversions API has a different schema. Out of scope until there is a fixture set for it.
- **Phone hash without `+`.** The first draft hashed `+15550102834`. Meta expects digits only with country code, so hashes from the draft would not match.
- **Score labeled as an estimate.** Meta does not publish the Event Match Quality formula. The README says so; the score is for comparing payloads.
- **Python 3.10+.** Python 3.9 is end-of-life and no longer available on `ubuntu-latest` runners; CI matrix is 3.10–3.14.
- **Pushed straight to `main`.** Requested directly for the initial release.

## Review fixes (branch `build/review-fixes`)

An independent review by a different model found 12 issues. Each was reproduced before fixing.

- **Fixed:** CLI crash on list/dict `action_source`, non-UTF-8 files and directories; empty `data` arrays passing; NaN/negative/zero/string `event_time` passing; unknown `action_source` and missing `event_source_url` on website events now errors (Meta rejects both); phone normalization for `00`, `(0)`, leading zeros, fullwidth digits, extensions; normalization helpers and `hash --field` for `fn ln ct st zp country ge db`; strict `fbc`/`fbp` format, and no score credit for malformed values; `event_id: 0` treated as present; duplicate `event_name`/`event_id` pairs in a batch flagged.
- **Changed, not as the review described:** the CI negative smoke test (`! capi-validator ...`) did fail correctly, because it was the step's last line. Rewritten as an explicit `if` so it stays correct if lines are added after it.
- **Declined:** making stale `event_time` (> 7 days) an error. The check runs against the clock at audit time, so replaying historical sGTM logs would fail every event. It stays a warning; `--strict` fails on it.
- **Known limit:** `db` normalization keeps digit order as given; it cannot tell `MM/DD/YYYY` from `DD/MM/YYYY`.
