# PROGRESS — v0.4.0 agentic

`Build log / v0.4.0` · Budget 4h, stop after 3 failed attempts on one problem

| Task | Status | Evidence |
|---|---|---|
| Spec approved (official MCP SDK, L3 fixture-verified), plan written | done | SPEC.md, PLAN.md |
| 1 Acceptance tests (separate agent, from SPEC + contract) | done | 20 tests; 2 passed before code existed |
| 2 Check registry; core routed through it | done | 26 codes; old suites unchanged |
| 3 JSON report v1, schema, `checks`, `explain` | done | AC2, AC3 pass |
| 4–5 Live module + `live quality` | done | AC12, AC13 pass; 10 extra unit tests incl. token-in-header capture |
| 6 MCP server, 5 tools | done | found: SDK pre-parses JSON strings → fixed; AC4–AC6 pass |
| 7 Network isolation | done | found: offline CLI loaded network code → fixed; AC7 passes |
| 8 Packaging | done | core wheel runs without extra; v0.4 acceptance 20/20 against installed wheel, none skipped |
| 9 Docs | done | Agentic section, layer diagram, AGENTS.md, rules table, recorded MCP session; `claude mcp add` → Connected |
