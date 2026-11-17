# PLAN — v0.2.0

`Build plan / v0.2.0` · Nov 2026 · Branch `build/standard` · Spec: [SPEC.md](SPEC.md)

Each task names its files and the check that proves it landed. `[x]` = verified.

| # | Task | Files | Verify |
|---|---|---|---|
| 1 [x] | Write acceptance tests from SPEC only (separate agent, before code changes) | `tests/test_acceptance.py` | file runs; failures list what is not built yet |
| 2 [x] | Fetch Meta docs; compare each rule; record source per rule | `docs/meta-rules.md` | every rule in `core.py`/`hashing.py` has a row with a source URL |
| 3 [x] | Fix any rule that disagrees with the docs | `core.py`, `hashing.py`, tests | new test per fix passes |
| 4 [x] | ruff + mypy + bandit config; fix findings | `pyproject.toml`, package, tests | AC8 commands exit 0 |
| 5 [x] | Glyph set in CLI output (`□ WARNING`) | `cli.py`, tests | grep finds no `!` marker; tests pass |
| 6 [x] | CI: quality job, build job (wheel+sdist, install wheel in clean venv, run AC flows from temp dir, upload artifact) | `.github/workflows/ci.yml` | CI green on PR; artifact present |
| 7 [x] | Recorded flows against installed wheel | `docs/transcripts/*.txt`, `scripts/record_transcripts.sh` | script reproduces committed files byte-for-byte |
| 8 [x] | README on FOCO skeleton + Mermaid diagram + rules table link | `README.md` | renders on github.com; brand gate 6/6 |
| 9 [x] | Version 0.2.0 + CHANGELOG | `pyproject.toml`, `__init__.py`, `CHANGELOG.md` | `capi-validator --version` → 0.2.0 |
| 10 | Security scan + review by a different model; fix confirmed findings | — | findings resolved or logged |
| 11 | Open draft PR with evidence | — | PR URL; CI green |
