# AGENTS.md — using CAPILinter from an agent

This file is for AI agents (Claude Code, Cursor, others) asked to check a Meta Conversions API setup with CAPILinter.

## Rules

1. **Quote, don't recompute.** Every verdict, code, score and hash comes from CAPILinter. Report what it returned; do not re-derive a severity, re-hash a value yourself, or invent a check it did not run.
2. **Cite the source.** Each issue carries `fix` and `source` (a Meta documentation URL). Use `explain_check` / `capilinter explain <CODE>` when the user asks why something matters.
3. **Read-only.** CAPILinter never sends events or changes anything at Meta. Don't use it as a reason to send test events or edit a live setup; propose the change and let the user make it.
4. **Absolute paths.** `audit_payload` refuses relative paths: the server's working directory is wherever your client started it. Pass `/abs/path.json` or `~/path.json`, or pass the JSON itself as `payload_json`.
5. **Mind the data.** Tool results reach the model behind you. If a payload holds raw PII, say so, and suggest hashing before sharing it further.
6. **Live mode is opt-in.** `read_dataset_quality` needs `META_ACCESS_TOKEN` in the server's environment. If it returns `error.kind = "credentials"`, tell the user; never ask them to paste a token into the chat.

## Which tool

| Goal | MCP tool | CLI |
|---|---|---|
| Is this payload safe to send? | `audit_payload` | `capilinter inspect FILE --json` |
| What exactly should this field contain? | `hash_value` | `capilinter hash VALUE --field KEY` |
| What does CAPILinter check? | `list_checks` | `capilinter checks --json` |
| Why does a finding matter, and what do I cite? | `explain_check` | `capilinter explain CODE --json` |
| How is Meta matching events on a dataset? | `read_dataset_quality` | `capilinter live quality --dataset-id ID --json` |

## Reading results

- `passed: false` means at least one ERROR (or, with `--strict`, a WARNING).
- Exit codes: `0` pass, `1` a check failed or no events, `2` bad input, missing token or Meta API error.
- The report shape is [docs/schema/report-v1.json](docs/schema/report-v1.json) (`schema_version: 1`).
- `emq_estimate` is CAPILinter's heuristic, not Meta's score. Meta's real Event Match Quality comes only from `read_dataset_quality` (`emq_score`). Never present one as the other.
- `EVENT_TIME_STALE` on old logs is expected: the check uses today's clock.

## Working on this repo

- Every issue code lives in `capilinter/checks.py`. Add a check there, emit it from `core.py` (or `live/quality.py`), add its row to `docs/meta-rules.md` with the Meta source, and add a test that triggers it. The acceptance tests fail if any of the four is missing.
- Only `capilinter/live/http.py` may import a network library.
- Gates: `ruff check . && ruff format --check . && mypy && bandit -q -r capilinter -c pyproject.toml`, then `python -m unittest discover -s tests`.
- Regenerate recorded output after changing CLI text: `bash scripts/record_transcripts.sh && python scripts/render_readme_images.py` (with the installed wheel first on `PATH`, as CI does).
