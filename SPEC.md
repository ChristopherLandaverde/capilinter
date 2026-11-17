# SPEC — bring server-side-capi-validator to the foco-build standard

`Build spec / v0.2.0` · Nov 2026 · Branch `build/standard` · Status: awaiting approval

Scope gate: this is a new public tool beside the current loop (AdLinter → focosys.io). Christopher asked to proceed on Nov 16, 2026; treated as an override.

## Problem

v0.1.0 works (32 tests, CI green on Python 3.10–3.14), but it was built before the build process. Nothing ties its rules to Meta's published requirements, CI runs no lint, typecheck or security scan, no built artifact is installed and exercised, and the README and CLI fail parts of the brand ship gate (the `!` glyph, no number as evidence, no slash label or diagram). Someone who finds the repo has no evidence they can check for why they should trust its verdicts.

## Who uses it, and what they decide

- **RevOps / analytics engineers** running sGTM or webhook CAPI pipelines decide: *is this payload safe to send, and if not, what do I fix first?*
- **Prospective clients reading the repo** decide: *does this person know CAPI well enough to own my pipeline?* The repo is evidence for focosys.io.

## In scope

1. **Rules traced to Meta's docs.** Each validation rule and normalization rule cites the Meta doc section it implements, in a rules table in the README and in code comments. Any rule that disagrees with the docs gets fixed.
2. **CI quality gates.** ruff (lint + format check) and mypy (strict on the package), configured in `pyproject.toml`, plus bandit, all in CI. Fix the current 32 ruff findings.
3. **Acceptance tests.** `tests/test_acceptance.py`, one test per criterion below, named `test_ac<N>_...`.
4. **Built-artifact check.** CI builds wheel and sdist, installs the *built wheel* in a clean venv, runs the CLI flows against it, and uploads the wheel as a run artifact. That run plays the role of a preview deploy.
5. **Recorded flows.** Transcripts of the primary flows run against the installed wheel are committed to `docs/transcripts/`: inspect pass, inspect fail, `--strict`, `--json`, `hash`. They stand in for screenshots.
6. **Brand ship gate.** README rebuilt on the FOCO skeleton (slash label, metadata line, trace block, scope, evidence numbers, CTA to christopher@focosys.io), plus a Mermaid diagram of where the tool sits in the pipeline. CLI output uses only the glyph set.
7. **Process record.** `SPEC.md`, `PLAN.md`, `PROGRESS.md`, `DECISIONS.md` in the repo.
8. **Version 0.2.0.** Version bumped to 0.2.0 with a `CHANGELOG.md`.

## Out of scope

LinkedIn or other CAPIs; calling the Graph API or sending events; publishing to PyPI; a reusable GitHub Action; packaging a release tag; ConsentFlow; AdLinter integration; any real client data (fixtures stay synthetic and labeled).

## Acceptance criteria (runnable)

| # | Criterion | Check |
|---|---|---|
| AC1 | Clean payload passes | `capi-validator inspect fixtures/valid_payload.json` → exit 0 |
| AC2 | Each broken fixture fails with its named code | `inspect fixtures/{unhashed_pii,unhashed_phone,missing_event_id}.json` → exit 1, output contains `RAW_PII_UNHASHED_EMAIL` / `RAW_PII_UNHASHED_PHONE` / `MISSING_EVENT_ID` |
| AC3 | Unreadable or non-CAPI input never crashes | directory, binary file, scalar JSON → exit 2, no traceback on stderr |
| AC4 | Hashes match Meta's documented normalization | `hash` output for each documented example input equals `sha256` of the documented normalized form |
| AC5 | `--strict` escalates warnings | a payload with only warnings → exit 0 default, exit 1 with `--strict` |
| AC6 | `--json` is machine-readable | output parses as JSON with `passed`, `events[].issues[].code` |
| AC7 | Built wheel works outside the repo | in a clean venv, `pip install dist/*.whl` then AC1–AC2 from a temp dir → same results |
| AC8 | Quality gates clean | `ruff check .`, `ruff format --check .`, `mypy`, `bandit -r server_side_capi_validator` → all exit 0 |
| AC9 | CI enforces AC1–AC8 | GitHub Actions on the PR green on Python 3.10–3.14 |
| AC10 | Brand ship gate | the 6 foco-brand checks pass, written up point by point in the PR |

## Assumptions, and how each is checked

- **The rules match Meta's current docs.** Checked by fetching Meta's *Customer Information Parameters* and *Server Event Parameters* pages during the build and comparing them rule by rule. Any mismatch is fixed or logged.
- **GitHub renders Mermaid in READMEs.** Checked by viewing the PR's README on github.com.
- **ruff and mypy are dev-only.** Runtime dependencies stay at zero. Checked by confirming `dependencies = []` in the built wheel's metadata.

## Decided by me, logged in DECISIONS.md

- Rule severities where Meta's docs are clear.
- Glyph for warnings: `□ WARNING`, meaning observed but not broken. The glyph set has no warning mark.
- ruff rule set and formatting.
- README structure within the brand skeleton.

## Brought back to you

- **Merging `build/standard` into `main`.** Red tier.
- **Any rule where Meta's docs are ambiguous.** I'll pick a default and flag it.
- **Repo topics and homepage.** The proxy here blocks repo settings, so you need to run one command (in the message).

Budget: $20, 4h. Review at the end by a different model than the one that writes the code.
