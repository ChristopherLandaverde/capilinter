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

## v0.3.0 rename (branch `build/rename-capilinter`)

- **Name: CAPILinter.** Christopher picked it on Nov 16, 2026 from three options (CAPILinter, CAPI Trace, Signal Verifier).
- **No `capi-validator` alias.** The old command was public for one day and was never on PyPI. One name is less to explain than a deprecated alias.
- **SPEC.md and PLAN.md keep the old name.** They record the v0.2.0 build as it happened.
- **Repository rename needs Christopher.** The GitHub proxy here refuses repository-settings writes. GitHub redirects the old URL after a rename.
- **README in AdLinter's format.** Christopher asked for it to look like AdLinter's README. Same structure (centered logo, tagline, stats line, badges, nav, intro, captioned demo image, Who it's for, What you get, Known limits, Privacy), same palette and type from AdLinter's DESIGN.md (paper `#FAFAF7`, navy `#1E3A8A`, severity colors only for findings).
- **Demo image generated, not captured.** A screenshot drifts from the code. The SVG is drawn from recorded CLI output and CI fails if it changes, so the picture is evidence.
- **Logo:** two signal lines, browser and server, merging into one event: deduplication, the tool's main job. Navy tile like AdLinter's, so the two read as one family.
- **Static badges** for version, Python and dependencies. They need no network service; the CI badge is live.

## v0.4.0 agentic (branch `build/agentic`, spec: SPEC.md)

- **Approved choices (Nov 16, 2026):** official MCP SDK as an optional `mcp` extra; L3 included, fixture-verified only.
- **MCP SDK 2.x.** The current SDK is 2.x (`MCPServer`, not 1.x `FastMCP`). Pinned `mcp>=2.3,<3`. The `dev` extra references `capilinter[mcp]` so the pin lives in one place.
- **One report builder** (`capilinter/report.py`) feeds the CLI and the MCP server, so their JSON is identical by construction; the CLI text is rendered from the same dict. Text output is unchanged (recorded runs identical).
- **`payload_json` accepts text or an already-parsed object.** The SDK parses JSON-looking string arguments before validation, so an agent sending the payload as text arrived as an object and was rejected. Found by the acceptance tests.
- **Network code is loaded only for `live`.** The acceptance test that disables sockets showed offline commands imported `urllib.request` at startup. Imports moved into the live command and MCP tool.
- **Token as `Authorization: Bearer` header,** not the `access_token` query parameter Meta's examples use, to keep it out of URLs and logs. Not verified against Meta's API; listed as a known limit.
- **Live flags are WARNINGs;** `--strict` fails on them. They report Meta's own measurements, not payload defects. Dedup-key coverage below 100% is flagged although Meta states no threshold (marked `□` in docs/meta-rules.md).
- **Test changes, both tightening:** the guard test asserted any `Exception`; it now asserts `RequestRefused` and that the allowed request passes. The packaging test treated `capilinter[mcp]` (the package's own extra) as an MCP dependency by substring match; it now compares the requirement name and also asserts the `mcp` extra exists.
- **`claude mcp add` verified** in a scratch project against the installed 0.4.0 wheel (`claude mcp list`: Connected), then removed. Claude Desktop and Cursor configs not run.
- **v0.2 build docs archived** to `docs/build/`; SPEC/PLAN/PROGRESS at the root now describe v0.4.0.
