<p align="center">
  <img src="docs/images/logo.png" width="96" height="96" alt="CAPILinter logo: two white signal lines, browser and server, merging into one event dot on a navy tile">
</p>

<h1 align="center">CAPILinter</h1>

<p align="center">
  <strong>A Conversions API event can be accepted and still fail to match or deduplicate. Check the payload before it leaves your server.</strong>
</p>

<p align="center">
  26 checks traced to Meta's docs · normalizes and hashes 10 customer fields · MCP server for Claude, Cursor and any MCP client · offline core, zero dependencies
</p>

<p align="center">
  <a href="https://github.com/ChristopherLandaverde/capilinter/actions/workflows/ci.yml"><img src="https://github.com/ChristopherLandaverde/capilinter/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/version-0.4.0-1E3A8A" alt="Version 0.4.0"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%2B-1E3A8A" alt="Python 3.10+"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/dependencies-0-1E3A8A" alt="Zero runtime dependencies"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-1E3A8A" alt="License: MIT"></a>
  <a href="#agentic"><img src="https://img.shields.io/badge/agentic-L1%C2%B7L2%C2%B7L3-1E3A8A" alt="Agentic: L1, L2 and L3"></a>
</p>

<p align="center">
  <a href="#agentic">For agents</a> · <a href="#try-it">Try it</a> · <a href="#what-it-checks">What it checks</a> · <a href="docs/meta-rules.md">Rules and sources</a> · <a href="#known-limits">Known limits</a> · <a href="#privacy">Privacy</a>
</p>

For engineers running Meta's Conversions API from sGTM, a webhook or their own server, and for anyone auditing a CAPI setup they didn't build. A raw email in `user_data`, a phone hashed with its `+`, a missing `event_id`, a timestamp in milliseconds: Meta can accept the request and still fail to match the user or deduplicate against the pixel. CAPILinter reads the payload JSON, says what is wrong, cites the rule, and prints the normalized hash to send instead. It never sends events to Meta. Your own agent can call the same checks through the local `capilinter-mcp` server, and read Meta's Dataset Quality API read-only; deciding what to change stays with you.

<p align="center">
  <img src="docs/images/fix-demo.svg" width="880" alt="Three-step fix on a synthetic Meta CAPI payload. Step 1: capilinter inspect reports RAW_PII_UNHASHED_EMAIL, estimated match quality 1.0 out of 10, result FAIL. Step 2: capilinter hash normalizes and hashes the email. Step 3: the same payload with the hashed email has no errors, estimated match quality 4.0 out of 10, result PASS.">
  <br><sub>Real CLI output on the bundled synthetic fixtures, no client data. CI regenerates this image from the installed package and fails if a line changes.</sub>
</p>

## Agentic

CAPILinter is built as an agentic tool in four layers: a deterministic engine, typed read-only tools over it, your own agent on top, and you deciding what to change. The tools give your agent the engine's codes, verdicts and Meta sources to quote, not recompute; the agent explains what came back.

<p align="center">
  <img src="docs/images/agentic-stack.svg" width="880" alt="CAPILinter's agentic stack in four layers. Layer 1, Engine: the check registry, 26 checks in capilinter/checks.py, each with why it matters, how to fix it and its Meta source. Layer 2, Tools: capilinter with JSON output and the capilinter-mcp server with audit_payload, hash_value, list_checks, explain_check and read_dataset_quality, read-only, enforced in code (L1 JSON, L2 MCP). Layer 3, Your agent: Claude, Cursor or any MCP client, reading Meta's Dataset Quality API read-only (L3 live read, fixture-verified). Layer 4, You decide: nothing writes or sends events; you make the change yourself from each finding's code, fix and source.">
</p>

| Ask your agent… | Tool | Reads | Writes |
|---|---|---|---|
| "Check the CAPI payload in ~/sgtm/logs/purchase.json and list what will fail." | `audit_payload` | The file you name (absolute or `~/` path), or JSON passed inline. No network. | nothing |
| "What should I send as `em` for Jane.Doe@Example.com?" | `hash_value` | The value you give | nothing |
| "Which dedup checks does CAPILinter run?" | `list_checks` | The check registry | nothing |
| "Why does `MISSING_EVENT_ID` matter? Give me the Meta page to cite." | `explain_check` | The registry entry: why, fix, Meta source | nothing |
| "How is Purchase matching on dataset 123456789?" | `read_dataset_quality` | Meta's Dataset Quality API (`GET` only, enforced in code), with your token | nothing |

Agentic levels: L1 machine-readable · L2 agent-callable · L3 live read. CAPILinter: L1 (`--json`, [schema v1](docs/schema/report-v1.json)) · L2 (`capilinter-mcp`) · L3 (fixture-verified: tested against synthetic API responses, not yet a real account). Read-only by design: nothing writes. Agent instructions: [AGENTS.md](AGENTS.md).

### MCP server

`capilinter-mcp` exposes the same engine as read-only [MCP](https://modelcontextprotocol.io) tools over stdio. It is an optional extra, so the core CLI stays dependency-free:

```bash
pip install "capilinter[mcp] @ git+https://github.com/ChristopherLandaverde/capilinter.git"
```

**Claude Code** (current project; `claude mcp add -s user ...` adds it for every project):

```bash
claude mcp add capilinter -- capilinter-mcp
```

**Claude Desktop** (`claude_desktop_config.json`) and **Cursor** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "capilinter": { "command": "capilinter-mcp" }
  }
}
```

If the app can't find `capilinter-mcp` on its `PATH`, use the absolute path from `which capilinter-mcp`. For `read_dataset_quality`, set `META_ACCESS_TOKEN` in the server's environment (`-e META_ACCESS_TOKEN=...` in `claude mcp add`, or an `"env"` object in the JSON); values set that way are stored in that client's config file.

The `claude mcp add` line was run against the installed 0.4.0 wheel and `claude mcp list` reported the server as connected. The Claude Desktop and Cursor snippets use the same command but weren't run.

Bad input (a relative path, a missing file, both a path and inline JSON, an unknown field or code, a missing token) comes back as a tool error, `{"error": {"kind": "usage" | "refused" | "credentials" | "api" | "internal", "message": "..."}}`, not a crash. `refused` means the tool declined rather than guess: a relative path, a value it cannot normalize, or a request the read-only guard stopped before sending. A [recorded session](docs/transcripts/13-mcp-session.txt) against the installed server shows `tools/list` and three calls; CI re-records it and fails on any difference.

**Where MCP results go:** every tool result goes to the agent that called it, and so to the model behind it, under that agent's data terms. That includes payload contents you pass in. Hash PII before you hand a payload to an agent if that matters to you.

### Live mode (L3, fixture-verified)

```bash
export META_ACCESS_TOKEN=...        # read from the environment only; never a flag, never printed
capilinter live quality --dataset-id 123456789
capilinter live quality --dataset-id 123456789 --json --strict
```

Reads `GET https://graph.facebook.com/v25.0/dataset_quality` for website events and reports Meta's own numbers per event: Event Match Quality, match-key coverage, Meta's diagnostics, event coverage against Meta's goal, dedup-key coverage and data freshness. It flags EMQ below the 6.0 Meta recommends, each Meta diagnostic, coverage below goal and server events missing `event_id`. The token needs at least Partial access → Use events dataset on the dataset. A request guard (`capilinter/live/http.py`) allows only that one `GET`; any other method, host or path is refused before a connection opens. See the [recorded run](docs/transcripts/12-live-quality.txt) on a synthetic response.

## Where it sits

<p align="center">
  <img src="docs/images/pipeline.svg" width="880" alt="The browser pixel sends an event with an event_id to Meta. Your server or sGTM container builds the Conversions API payload for the same event. CAPILinter checks that payload offline against 21 rules traced to Meta's docs. Exit 0: send it, and Meta deduplicates it against the pixel event by event_name and event_id. Exit 1: a fix list with the code, the field and the fix. CAPILinter never sends events.">
</p>

## Who it's for

| You are | You come to |
|---|---|
| An engineer shipping CAPI from sGTM or server code | Fail the build before a payload with raw PII or a missing dedup key reaches production |
| A consultant auditing a CAPI setup you didn't build | Hand over a list of findings, each with a code, the field and the rule in Meta's docs |
| An analyst whose Events Manager numbers don't match the CRM | Check whether the payload is the reason before blaming attribution |

## What you get

- **Know where PII leaves unhashed.** Raw emails and phones in `user_data`, uppercase or malformed hashes on any of the 10 customer fields.
- **Know whether pixel and server events will deduplicate.** Missing `event_id`, repeated `event_name` + `event_id` pairs in one batch, malformed `fbc` and `fbp`.
- **Know whether Meta will take the event at all.** `event_time` in milliseconds, in the future, or older than 7 days; unknown `action_source`; website events without `client_user_agent` or `event_source_url`.
- **The hash to send instead.** `capilinter hash` normalizes email, phone, name, city, state, zip, country, gender and date of birth the way Meta documents, and refuses values it would have to guess.
- **A rule you can point to.** Each check has a code and a row in [docs/meta-rules.md](docs/meta-rules.md) citing the Meta page it comes from.

## Try it

```bash
pip install "git+https://github.com/ChristopherLandaverde/capilinter.git"
git clone https://github.com/ChristopherLandaverde/capilinter.git && cd capilinter
capilinter inspect fixtures/unhashed_pii.json            # the failing step above
capilinter inspect fixtures/unhashed_pii_repaired.json   # the passing step
```

Then point it at your own payload: a single event, an array of events, or a full `{"data": [...]}` request body.

## Use it

```bash
capilinter inspect payload.json            # check a payload
capilinter inspect payload.json --strict   # warnings fail the run too
capilinter inspect payload.json --json     # machine-readable report for CI
capilinter hash "  John_Smith@gmail.com "   # sha256 of john_smith@gmail.com
capilinter hash "(650)555-1212" --phone     # sha256 of 16505551212
capilinter hash "07911 123456" --phone --country-code 44   # sha256 of 447911123456
capilinter hash "2/16/1997" --field db      # sha256 of 19970216
```

| Exit | Meaning |
|---|---|
| `0` | Every event passed |
| `1` | A check failed, or the file has no events |
| `2` | Unreadable file, invalid JSON, a non-CAPI shape, or a value `hash` cannot normalize |

Errors always fail the run. Warnings (stale `event_time`, uppercase hashes, malformed `fbc`/`fbp`, duplicate IDs in a batch) fail it only under `--strict`. Staleness is a warning because the check uses the clock at audit time, so replaying last month's sGTM logs would flag every event. Use `--strict` on payloads you are about to send.

Every flow above has a [recorded run](docs/transcripts/) of real output.

## What it checks

| Area | Checks | Codes |
|---|---|---|
| Required fields | `event_name`, `event_time`, `action_source`, `user_data`; `client_user_agent` and `event_source_url` on website events | `MISSING_*`, `INVALID_ACTION_SOURCE`, `NO_CUSTOMER_INFORMATION` |
| Timestamps | seconds not milliseconds, not in the future, not NaN or text, at most 7 days old | `EVENT_TIME_*`, `INVALID_EVENT_TIME_*` |
| Deduplication | `event_id` present; no repeated `event_name` + `event_id` in a batch | `MISSING_EVENT_ID`, `DUPLICATE_EVENT_ID` |
| Hashing | `em ph fn ln ct st zp country ge db` are lowercase SHA-256; raw email and phone named as such | `RAW_PII_UNHASHED_*`, `INVALID_SHA256`, `HASH_NOT_LOWERCASE` |
| Browser IDs | `fbc` and `fbp` match `fb.<0-2>.<13-digit ms timestamp>.<id>`, unhashed | `MALFORMED_FBC`, `MALFORMED_FBP` |
| Live (L3) | Meta's EMQ ≥ 6.0, Meta diagnostics, event coverage vs goal, server events carrying `event_id` | `LIVE_*` |

All 26 checks, their Meta sources, and the 7 rules that v0.1 got wrong are in [docs/meta-rules.md](docs/meta-rules.md). `capilinter checks` lists them; `capilinter explain <CODE>` prints why it matters, how to fix it and the source.

<details>
<summary>How <code>capilinter hash</code> normalizes each field</summary>

| Field | Normalize | Example |
|---|---|---|
| `em` | trim, lowercase | `John_Smith@gmail.com` → `john_smith@gmail.com` |
| `ph` | digits only, country code, no `+`, `00`, `(0)` or leading zeros; extensions dropped | `(650)555-1212` → `16505551212` |
| `fn`, `ln` | lowercase letters, UTF-8 kept | `Valéry` → `valéry` |
| `ct` | lowercase letters, no spaces | `New York` → `newyork` |
| `st` | lowercase letters | `AZ` → `az` |
| `zp` | lowercase, no spaces or dashes; US first 5 digits | `94035-1234` → `94035`, `M1 1AE` → `m11ae` |
| `country` | 2-letter ISO code; anything else refused | `US` → `us` |
| `ge` | `f` or `m` | `Female` → `f` |
| `db` | `YYYYMMDD`, real dates only | `2/16/1997` → `19970216` |

A national number starting with `0` is refused under the default `--country-code 1` instead of being given a US code. Pass its country code or write it with `+`.

</details>

<details>
<summary>Estimated match quality</summary>

Meta does not publish its Event Match Quality formula. CAPILinter's score is a weighted heuristic for comparing payloads, not a prediction of the number in Events Manager.

| Parameter | Weight |
|---|---|
| Hashed email (`em`) | 3.0 |
| Hashed phone (`ph`) | 2.5 |
| Click ID (`fbc`) | 1.5 |
| Browser ID (`fbp`) | 1.0 |
| `external_id` | 1.0 |
| `client_ip_address` | 0.5 |
| `client_user_agent` | 0.5 |

A parameter counts only when its value is valid. Grades: EXCELLENT ≥ 8.5 · GOOD ≥ 7.0 · FAIR ≥ 5.0 · POOR below 5.0.

</details>

## Known limits

- `inspect` checks **payloads, not live traffic**. It can't see whether your server actually sent the event or what Meta's response was. `live quality` reads what Meta reports, not individual events.
- Live mode is fixture-verified only: it has not been run against a real Meta dataset or token. It sends the token as an `Authorization: Bearer` header rather than the `access_token` query parameter in Meta's examples, to keep it out of URLs; that form is not yet verified against Meta's API.
- Rules follow Meta's docs as fetched on Nov 17, 2026. Meta can change them; [docs/meta-rules.md](docs/meta-rules.md) records what was checked.
- Meta CAPI only. LinkedIn, TikTok and other conversion APIs use different schemas.
- `hash` does not map names to codes: `United States` and `California` are refused or kept as words. Send `us` and `ca`.
- Ambiguous dates such as `03/04/1997` are read month-first, following Meta's own example. Send `YYYY-MM-DD` to avoid guessing.
- Meta requires only "at least one" `user_data` parameter, so an event with just an IP address passes. Its estimated match quality will be POOR.

## Privacy

- **Runs on your machine.** `inspect`, `hash`, `checks`, `explain` and the matching MCP tools make no network requests, and a test enforces it. Payloads are read from the file you name and never leave it.
- **Live mode** calls one endpoint, `GET https://graph.facebook.com/v25.0/dataset_quality`, with the token from `META_ACCESS_TOKEN`. All network code lives in `capilinter/live/http.py`; a test checks no other module imports a network library.
- **No telemetry.** Nothing is logged or sent anywhere.
- **Fixtures are synthetic.** Every file in `fixtures/` is made up; none comes from a client.

## Development

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests -v       # 86 unit and acceptance tests
ruff check . && ruff format --check . && mypy && bandit -q -r capilinter -c pyproject.toml
bash scripts/record_transcripts.sh            # regenerate docs/transcripts
python scripts/render_readme_images.py        # regenerate docs/images/fix-demo.svg
```

These are the commands CI runs on every push and pull request to `main`, on Python 3.10–3.14. CI also builds the wheel; checks the core installs and runs without the MCP extra; installs it with the extra in a clean environment; reruns both acceptance suites from outside the repo; and fails if the transcripts, the recorded MCP session or the demo image change. The build record is in [SPEC.md](SPEC.md), [PLAN.md](PLAN.md), [PROGRESS.md](PROGRESS.md) and [DECISIONS.md](DECISIONS.md); version history in [CHANGELOG.md](CHANGELOG.md).

Built by Christopher Landaverde at [FOCO Systems](https://focosys.io). Sibling tool: [AdLinter](https://github.com/ChristopherLandaverde/adlinter) for GTM and Google Ads. If your CAPI numbers don't match what your CRM says happened: christopher@focosys.io

## License

[MIT](LICENSE)
