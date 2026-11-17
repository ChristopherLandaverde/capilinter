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

## v0.2.0 (branch `build/standard`, spec: SPEC.md)

- **Scope override.** This is a new public tool beside the AdLinter → focosys.io loop. Christopher said to proceed on Nov 16, 2026.
- **Acceptance tests written by a separate agent** from SPEC.md only, before the code changes, so the agent writing the code did not write its own acceptance checks.
- **`event_id` stays an ERROR** although Meta marks it optional. Without it, browser/server deduplication fails, and that is this tool's purpose. Recorded with status `□` in docs/meta-rules.md.
- **`country` refuses full names** instead of mapping them to codes. A name-to-code table is a dependency or a large data file; refusing with a reason is boring and correct.
- **`db` reads ambiguous dates month-first** (US), following Meta's own `2/16/1997` example. Day-first is used only when the first number is above 12.
- **ruff ignores E501 and RUF001.** `ruff format` owns line length, and long user-facing messages read better unbroken. The glyphs `× □ ✓` and the fullwidth-digit test data are intentional.
- **`□ WARNING` for warnings.** The brand glyph set has no warning mark; `□` means observed, not broken.
- **"Preview deploy" for a CLI** is the CI package job: build the wheel and sdist, install the wheel in a clean venv, run the acceptance tests and CLI flows from outside the repo, and upload the wheel as an artifact.
- **Text transcripts instead of screenshots.** The output is terminal text, so a byte-exact transcript is stronger evidence than a picture. CI regenerates them and fails on any difference.
- **Single build agent for code changes.** The tasks touched the same files (`core.py`, `hashing.py`, `cli.py`), so parallel worktrees would have produced merge conflicts, not speed. Independence comes from the separate acceptance-test agent and the final review by a different model.
- **Repo topics and homepage not set.** The GitHub proxy in this session refuses repository-settings writes (HTTP 403). One `gh repo edit` command for Christopher.

### Second independent review (v0.2.0)

A different model reviewed `build/standard`; no high-severity findings. Each finding was reproduced before acting.

- **Fixed:** national `0…` phone numbers no longer get a US `1` (refused under the default code, prepended with `--country-code` otherwise); combining marks kept in names and cities; impossible dates refused; `ge` limited to `f m female male`; `fbc`/`fbp` require a 13-digit ms timestamp (fixture updated); `✓ VERIFIED` no longer printed beside warnings; `--strict` pass on a fresh valid event now tested; `--json` reports empty payloads as JSON; the CI test matrix installs dev tools so AC8 runs there instead of skipping; doc counts corrected.
- **Declined:** requiring identifiers beyond Meta's literal "at least one user_data parameter". The tool follows the doc; the match-quality score shows the weakness.
- **Declined:** mapping US state names to codes. A lookup table for one field is not worth it; documented as a known limit.
