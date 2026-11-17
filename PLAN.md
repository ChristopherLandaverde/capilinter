# PLAN — v0.4.0 agentic

`Build plan / v0.4.0` · Nov 2026 · Branch `build/agentic` · Spec: [SPEC.md](SPEC.md)

## Interface contract (tests are written against this before code)

**Registry** — `capilinter/checks.py`: `CHECKS: dict[str, Check]`, `Check(code, severity, area, title, why, fix, source)`; `area` ∈ `required, timestamps, dedup, hashing, browser_ids, live`.

**CLI**
- `capilinter inspect FILE --json` → `{"schema_version": 1, "file", "passed", "batch_issues": [...], "events": [{"index", "event_name", "event_id", "valid", "issues": [{"severity", "code", "message", "field", "fix", "source"}], "emq_estimate": {...}}]}`. Schema: `docs/schema/report-v1.json` (JSON Schema draft 2020-12).
- `capilinter checks [--json]` → list of `{"code", "severity", "area", "title", "why", "fix", "source"}`.
- `capilinter explain CODE [--json]` → one such object; unknown code → exit 2.
- `capilinter live quality --dataset-id ID [--agent-name NAME] [--json] [--strict]`. The token comes from env `META_ACCESS_TOKEN`; if it's missing → exit 2. The JSON shape is `{"schema_version": 1, "dataset_id", "api_version": "v25.0", "passed", "events": [{"event_name", "emq_score", "match_keys": [{"identifier", "coverage"}], "diagnostics": [{"name", "description", "solution", "percentage", "affected_event_count", "total_event_count"}], "event_coverage": {"percentage", "goal_percentage"} | null, "dedupe": [{"dedupe_key", "browser_percentage", "server_percentage", "overall_browser_coverage"}], "data_freshness": str | null, "issues": [...]}]}`.
- Fixture mode: env `CAPILINTER_LIVE_FIXTURE=/abs/path.json` makes the transport return that file's body instead of the network. The request guard still runs on the URL that would have been called.
- Live codes, all WARNING:
  - `LIVE_EMQ_BELOW_RECOMMENDED` (< 6.0)
  - `LIVE_SERVER_DEDUP_KEY_LOW` (server events with `event_id` < 100%)
  - `LIVE_EVENT_COVERAGE_BELOW_GOAL`
  - `LIVE_EMQ_DIAGNOSTIC` (one per Meta diagnostic)

  `--strict` fails on them.
- Meta API error body (`{"error": {...}}`) → exit 2, message from Meta, token redacted.

**MCP** — console script `capilinter-mcp` (stdio), module `capilinter.mcp_server`. The tools are below. Every result is JSON text. Errors return `isError: true` with `{"error": {"kind": "usage"|"refused"|"credentials"|"api"|"internal", "message"}}`.
- `audit_payload(path?: str, payload_json?: str)`: exactly one of the two; `path` must be absolute or `~`.
- `hash_value(field: str, value: str, country_code: str = "1")` → `{"field", "normalized", "sha256"}`.
- `list_checks(severity?: str, area?: str)`.
- `explain_check(code: str)`.
- `read_dataset_quality(dataset_id: str, agent_name?: str)`.

**Network** — only `capilinter/live/http.py` may import `urllib`, `http.client` or `socket`.

## Tasks

| # | Task | Files | Verify |
|---|---|---|---|
| 1 [x] | Acceptance tests from SPEC + this contract (separate agent) | `tests/test_acceptance_v04.py`, `fixtures/live/*.json` | runs; failures list what is not built |
| 2 [x] | Check registry; core emits only registered codes | `capilinter/checks.py`, `core.py` | AC1 test |
| 3 [x] | JSON report v1 + schema; `checks`, `explain` | `cli.py`, `docs/schema/report-v1.json` | AC2, AC3 |
| 4 [x] | Live module: guard, transport, parser, findings | `capilinter/live/{__init__,http,quality}.py` | AC12, AC13 |
| 5 [x] | `live quality` CLI | `cli.py` | AC12, AC13 |
| 6 [x] | MCP server, 5 tools | `capilinter/mcp_server.py`, `pyproject.toml` | AC4–AC6 |
| 7 [x] | Network isolation test | `tests/` | AC7 |
| 8 [x] | Packaging: `mcp` extra, `capilinter-mcp` script, zero core deps | `pyproject.toml`, CI | AC8, AC9 |
| 9 [x] | Docs: README Agentic section + layer diagram, AGENTS.md, rules table, recorded MCP call, CHANGELOG | `README.md`, `AGENTS.md`, `docs/images/agentic-stack.svg`, `docs/meta-rules.md` | brand gate |
| 10 | Gates, CI, review by a different model; fix | — | AC10, AC11 |
