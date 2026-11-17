# Changelog

## 0.4.0 — Nov 2026

**Agentic: L1 · L2 · L3**, matching AdLinter's levels.

- **Check registry** (`capilinter/checks.py`): all 26 codes with severity, area, why, fix and Meta source. The validator emits only registered codes; tests keep the registry, the code and `docs/meta-rules.md` in step.
- **L1:** the JSON report has `schema_version: 1` and a JSON Schema (`docs/schema/report-v1.json`); each issue carries `fix` and `source`. New `capilinter checks` and `capilinter explain <CODE>`.
- **L2:** `capilinter-mcp`, an MCP server over stdio with five read-only tools: `audit_payload`, `hash_value`, `list_checks`, `explain_check`, `read_dataset_quality`. Optional extra: `pip install "capilinter[mcp]"`; the core stays dependency-free.
- **L3 (fixture-verified):** `capilinter live quality --dataset-id ID` reads Meta's Dataset Quality API read-only and flags EMQ below 6.0, Meta diagnostics, event coverage below goal and server events missing `event_id`. Token from `META_ACCESS_TOKEN` only, sent as a header; a request guard allows only `GET /v25.0/dataset_quality`.
- `AGENTS.md`; README Agentic section with layer diagram; recorded `explain`, live and MCP runs, re-checked in CI.
- Offline commands never load network code; only `capilinter/live/http.py` imports a network library.
- Hardening from independent review: redirects refused (they would carry the token); token trimmed, validated and redacted from every error; `hash` refuses values that normalize to nothing; 10 MB / 5,000-event input limits; JSON errors for wrong MCP argument types; every check code proven triggerable by a test.


## 0.3.0 — Nov 2026

**Renamed** to CAPILinter, to sit beside AdLinter under the FOCO naming rule: a public tool is named for what it checks.

- Repository, package and import name: `capilinter` (was `server-side-capi-validator` / `server_side_capi_validator`).
- Command: `capilinter` (was `capi-validator`). Same subcommands and flags.
- README rebuilt in AdLinter's format: logo, badges, a three-step fix demo and a pipeline diagram, both drawn on AdLinter's paper-tile palette.
- The demo image is generated from recorded CLI output (`scripts/render_readme_images.py`); CI regenerates it and fails on any difference.
- New synthetic fixture `fixtures/unhashed_pii_repaired.json` and two recorded runs for the demo's fix.
- No rule or behavior changes.

## 0.2.0 — Nov 2026

Every rule is now traced to Meta's docs ([docs/meta-rules.md](docs/meta-rules.md)). Six normalization rules disagreed with those docs and are fixed.

**Fixed**
- `country`: `United States` became `un`; non-2-letter values are now refused.
- `db`: `2/16/1997` became `02161997`; US `M/D/YYYY`, `D/M/YYYY` (day > 12), `YYYY-MM-DD` and `YYYYMMDD` now give `19970216`. Out-of-range dates are refused.
- `ct`: accented letters were stripped (`São Paulo` → `sopaulo`).
- `st`: every value was cut to 2 characters, breaking non-US states.
- `ge`: any value was cut to its first letter (`fluid` → `f`); now only `f m female male`.
- `user_data`: any parameter now satisfies Meta's "at least one" rule (was: one of six keys).
- CLI crashes on non-string `action_source`, non-UTF-8 files and directories; empty payloads passing; NaN/negative/string `event_time` passing.
- `ph`: a national number with a trunk `0` (UK `07911 123456`) got a US `1`; now it needs `--country-code` or a `+`. Also handles `00` and `(0)` prefixes, Unicode digits, extensions.
- `fn`/`ln`/`ct`/`st`: combining marks were dropped (`जॉन` → `जन`).
- `db`: impossible dates such as `02/30/1997` were accepted.

**Added**
- `hash --field` for `fn ln ct st zp country ge db`; `hash` exits 2 with a reason when a value cannot be normalized.
- Errors for unknown `action_source` and missing website `event_source_url`; duplicate `event_name`/`event_id` warnings within a batch; strict `fbc`/`fbp` format.
- Acceptance tests AC1–AC8, run against the source tree and against the installed wheel.
- CI quality gates (ruff, ruff format, mypy --strict, bandit) and a package job that builds, installs and exercises the wheel, then uploads it.
- Recorded CLI flows in [docs/transcripts/](docs/transcripts/), checked in CI.

**Changed**
- Requires Python 3.10+.
- Warnings print as `□ WARNING`. An event with no errors but some warnings prints `□ OBSERVED  no errors, N warnings` instead of `✓ VERIFIED`.
- `fbc`/`fbp` must carry a 13-digit millisecond timestamp.
- `--json` prints a JSON report for empty payloads too.

## 0.1.0 — Nov 2026

Initial release.
