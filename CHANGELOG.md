# Changelog

## 0.2.0 — Nov 2026

Every rule is now traced to Meta's docs ([docs/meta-rules.md](docs/meta-rules.md)). Five normalization rules disagreed with those docs and are fixed.

**Fixed**
- `country`: `United States` became `un`; non-2-letter values are now refused.
- `db`: `2/16/1997` became `02161997`; US `M/D/YYYY`, `D/M/YYYY` (day > 12), `YYYY-MM-DD` and `YYYYMMDD` now give `19970216`. Out-of-range dates are refused.
- `ct`: accented letters were stripped (`São Paulo` → `sopaulo`).
- `st`: every value was cut to 2 characters, breaking non-US states.
- `ge`: values other than `f`/`m` passed through; now refused.
- `user_data`: any parameter now satisfies Meta's "at least one" rule (was: one of six keys).
- CLI crashes on non-string `action_source`, non-UTF-8 files and directories; empty payloads passing; NaN/negative/string `event_time` passing.
- Phone normalization: `00` and `(0)` prefixes, leading zeros, Unicode digits, extensions.

**Added**
- `hash --field` for `fn ln ct st zp country ge db`; `hash` exits 2 with a reason when a value cannot be normalized.
- Errors for unknown `action_source` and missing website `event_source_url`; duplicate `event_name`/`event_id` warnings within a batch; strict `fbc`/`fbp` format.
- Acceptance tests AC1–AC8, run against the source tree and against the installed wheel.
- CI quality gates (ruff, ruff format, mypy --strict, bandit) and a package job that builds, installs and exercises the wheel, then uploads it.
- Recorded CLI flows in [docs/transcripts/](docs/transcripts/), checked in CI.

**Changed**
- Requires Python 3.10+.
- Warnings print as `□ WARNING`.

## 0.1.0 — Nov 2026

Initial release.
