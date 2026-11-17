# SPEC — CAPILinter v0.4.0, agentic

`Build spec / v0.4.0` · Nov 2026 · Branch `build/agentic` · Status: awaiting approval · Earlier builds: [docs/build/](docs/build/)

Scope gate: this adds to CAPILinter while AdLinter → focosys.io is still the current loop. Christopher asked for it on Nov 16, 2026; treated as an override.

## Problem

CAPILinter is a good tool for a person at a terminal. An agent (Claude Code, Claude Desktop, Cursor) can shell out to it, but it has to guess the flags, parse text, and re-explain findings from memory. There is no way for the agent to ask "what does `MISSING_EVENT_ID` mean, and where does Meta say so?" AdLinter already solved this with three levels. CAPILinter should match them, so the two tools work the same way for an agent.

## Who uses it, and what they decide

- **An engineer's agent** working in an sGTM or server repo. It decides: *is this payload safe to ship, and what exact change fixes it?* It must quote CAPILinter's verdicts, not invent its own.
- **A consultant's agent** auditing a client's CAPI setup. It decides: *what goes in the findings list, and what does each cite?*
- **Christopher, as a seller.** The README shows "agentic L1 · L2" next to AdLinter's badge, as evidence for focosys.io.

## In scope

1. **One check registry.** A single source of truth in `capilinter/checks.py` holds every issue code: severity, title, why it matters, how to fix it, and the Meta source URL. Today the codes live inline in `core.py`. `core.py` will emit only registered codes, and a test proves the registry, the code and `docs/meta-rules.md` agree.
2. **L1, machine-readable.**
   - The JSON report gets `"schema_version": 1`, and each issue carries `fix` and `source`.
   - A JSON Schema file documents the report, and a test validates real output against it.
   - New `capilinter checks [--json]` and `capilinter explain <CODE> [--json]` commands.
3. **L2, agent-callable.** A `capilinter-mcp` MCP server over stdio with four read-only tools that call the library and compute nothing themselves:
   - `audit_payload`: an absolute path *or* JSON text in, the L1 report out.
   - `hash_value`: field, value and country code in, the normalized value and its SHA-256 out, or a refusal with the reason.
   - `list_checks`: the registry, filterable by severity and area.
   - `explain_check`: one code, with why, fix and source.

   Bad input comes back as `{"error": {"kind": "usage" | "refused" | "internal", "message": ...}}`, matching AdLinter, never as a crash. Relative paths are refused.
4. **Agent docs.**
   - A README "Agentic" section in AdLinter's format: a layer diagram, an "Ask your agent…" table, and setup lines for Claude Code, Claude Desktop and Cursor.
   - A real recorded MCP call, run in CI.
   - `AGENTS.md`, telling any agent how to use the tool and not to recompute verdicts.
5. **Privacy statement for MCP.** The server makes no network calls, and a test enforces that. Tool results go to the model behind the agent, and the README says so plainly, as AdLinter's does.
6. **Version 0.4.0.** CHANGELOG, DECISIONS and PROGRESS updated.

## Out of scope

- L3 live read (Meta's APIs, Events Manager, dataset quality). It needs Meta access tokens; see question 2.
- Sending events, or any write to Meta.
- Publishing to PyPI or an MCP registry.
- LinkedIn or other conversion APIs.
- Real client data.

## Acceptance criteria (runnable)

| # | Criterion | Check |
|---|---|---|
| AC1 | Registry is the single source | test: every code `core.py` can emit is in the registry; every registry code has a test that triggers it; every code appears in `docs/meta-rules.md` |
| AC2 | JSON report is versioned and valid | `capilinter inspect <fixture> --json` validates against `docs/schema/report-v1.json` for every fixture; `schema_version == 1` |
| AC3 | `checks` and `explain` work | `capilinter checks --json` lists every registry code; `capilinter explain MISSING_EVENT_ID --json` returns why, fix and a `developers.facebook.com` source; unknown code → exit 2 |
| AC4 | MCP server lists exactly 4 read-only tools | stdio client: `tools/list` returns `audit_payload`, `hash_value`, `list_checks`, `explain_check` |
| AC5 | MCP results equal CLI results | `audit_payload` on each fixture returns JSON identical to `capilinter inspect --json`; `hash_value` equals `capilinter hash` |
| AC6 | MCP bad input is a tool error, not a crash | relative path, missing file, both path and text, unknown field → `error.kind` is `usage` or `refused`; the server stays up for the next call |
| AC7 | No network | test: importing and running the package with sockets disabled passes every MCP and CLI flow |
| AC8 | Core stays dependency-free | built wheel: no runtime `Requires-Dist`; the MCP SDK only under the `mcp` extra; `capilinter` CLI works without it |
| AC9 | Installed-wheel run | AC2–AC6 pass against `pip install dist/*.whl[mcp]` in a clean venv, from outside the repo |
| AC10 | Gates and CI | ruff, ruff format, mypy --strict, bandit clean; CI green on Python 3.10–3.14 |
| AC11 | Brand gate and review | foco-brand checks pass point by point; review by a different model, findings fixed or logged |

## Assumptions, and how each is checked

- **The official MCP Python SDK (`mcp`) supports Python 3.10+.** Checked by installing it in CI on 3.10 and 3.14.
- **`claude mcp add capilinter -- capilinter-mcp` connects in Claude Code.** Checked by running a real stdio client in CI. The `claude mcp add` line itself is marked "not run here" unless I can run it.
- **Meta's docs are unchanged since Nov 17.** Spot-checked by refetching both pages; any change is logged.

## Decided by me, logged in DECISIONS.md

- Tool names and argument shapes, kept parallel to AdLinter's `audit_export` / `list_checks` / `explain_check`.
- Registry wording for each code's why and fix.
- JSON Schema draft version.
- The layer diagram's wording, in AdLinter's palette.

## Brought back to you

1. **The MCP library.** Recommended: the official `mcp` SDK as an *optional* extra (`pip install "capilinter[mcp]"`). The core stays at zero dependencies and protocol details stay correct as MCP evolves. The alternative is a hand-written stdio JSON-RPC server: zero dependencies everywhere, but more code to keep in step with the protocol.
2. **L3 live read.** Recommended: not in this build. Reading Meta's dataset quality data needs a Meta access token, which means creating secrets, and it touches live client stacks. Both are red tier. A later build could add it fixture-verified, as AdLinter did.
3. **Merging into `main`.** Red tier, as before.

Budget: 4h wall clock, 3 failed attempts per problem. Review at the end by a different model than the one that writes the code.
