"""capilinter-mcp: CAPILinter as read-only MCP tools over stdio.

Install with `pip install "capilinter[mcp]"`, then point an MCP client at the
`capilinter-mcp` command. Every tool calls the same library code as the CLI;
nothing here computes a verdict, a score or a hash on its own.

Errors come back as tool results with isError set and a JSON body
{"error": {"kind": "usage" | "refused" | "credentials" | "api" | "internal", "message": ...}}.
"""

import json
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
    from mcp.types import CallToolResult, TextContent, ToolAnnotations

    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    MCP_AVAILABLE = False

from . import __version__, checks
from .hashing import normalize_and_hash_field, normalize_value
from .report import InputError, build_report, load_json_file, load_json_text

HASHABLE_FIELDS = ("em", "ph", "fn", "ln", "ct", "st", "zp", "country", "ge", "db")
SEVERITIES = (checks.ERROR, checks.WARNING)

INSTRUCTIONS = (
    "CAPILinter checks Meta Conversions API payloads offline and reads Meta's Dataset Quality API read-only. "
    "Quote its verdicts, codes and numbers; do not recompute them. Use explain_check for why a finding "
    "matters, how to fix it and the Meta source to cite. Nothing here sends events or writes to Meta."
)


class ToolFailure(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def _ok(obj: Any) -> str:
    return json.dumps(obj, indent=2)


def _fail(kind: str, message: str) -> "CallToolResult":
    body = json.dumps({"error": {"kind": kind, "message": message}})
    return CallToolResult(content=[TextContent(type="text", text=body)], is_error=True)


# Tool logic as plain functions, so it is testable without the MCP SDK.


def audit_payload_impl(path: Any = None, payload_json: Any = None) -> dict[str, Any]:
    if path is not None and not isinstance(path, str):
        raise ToolFailure("usage", "path must be a string: an absolute file path or ~/...")
    if payload_json is not None and not isinstance(payload_json, (str, dict, list)):
        raise ToolFailure("usage", "payload_json must be JSON text, a JSON object or a JSON array.")
    has_payload = payload_json is not None and payload_json != ""
    if bool(path) == has_payload:
        raise ToolFailure("usage", "Pass exactly one of path (absolute file path) or payload_json (the JSON text).")
    try:
        if path:
            try:
                p = Path(path).expanduser()
            except RuntimeError as exc:  # e.g. ~unknownuser
                raise ToolFailure("usage", f"Cannot expand {path!r}: {exc}") from None
            if not p.is_absolute():
                raise ToolFailure(
                    "refused",
                    f"Relative path {path!r} refused: the server's working directory is wherever the agent started it. "
                    "Pass an absolute path or ~/...",
                )
            report, _ = build_report(load_json_file(p), str(p))
        else:
            # MCP clients and SDKs may hand over JSON text already parsed; accept both.
            data = load_json_text(payload_json) if isinstance(payload_json, str) else payload_json
            report, _ = build_report(data, "<payload_json>")
    except InputError as exc:
        raise ToolFailure(exc.kind, exc.message) from None
    return report


def hash_value_impl(field: Any, value: Any, country_code: Any = "1") -> dict[str, str]:
    if not isinstance(value, str) or not isinstance(country_code, str):
        raise ToolFailure("usage", "value and country_code must be strings.")
    if field not in HASHABLE_FIELDS:
        raise ToolFailure("usage", f"field must be one of {', '.join(HASHABLE_FIELDS)}; got {field!r}.")
    try:
        normalized = normalize_value(field, value, country_code)
        digest = normalize_and_hash_field(field, value, country_code)
    except ValueError as exc:
        raise ToolFailure("refused", f"Cannot normalize without guessing: {exc}") from None
    return {"field": field, "normalized": normalized, "sha256": digest}


def list_checks_impl(severity: Any = None, area: Any = None) -> list[dict[str, str]]:
    if (severity is not None and not isinstance(severity, str)) or (area is not None and not isinstance(area, str)):
        raise ToolFailure("usage", "severity and area must be strings when given.")
    if severity is not None and severity.upper() not in SEVERITIES:
        raise ToolFailure("usage", f"severity must be one of {', '.join(SEVERITIES)}; got {severity!r}.")
    if area is not None and area not in checks.AREAS:
        raise ToolFailure("usage", f"area must be one of {', '.join(checks.AREAS)}; got {area!r}.")
    return [
        c.to_dict()
        for c in checks.CHECKS.values()
        if (severity is None or c.severity == severity.upper()) and (area is None or c.area == area)
    ]


def explain_check_impl(code: Any) -> dict[str, str]:
    if not isinstance(code, str) or not code.strip():
        raise ToolFailure("usage", "code must be a check code string, e.g. MISSING_EVENT_ID.")
    check = checks.CHECKS.get(code.strip().upper())
    if check is None:
        raise ToolFailure("usage", f"Unknown check code {code!r}. Call list_checks for the codes.")
    return check.to_dict()


def read_dataset_quality_impl(dataset_id: Any, agent_name: Any = None, strict: Any = False) -> dict[str, Any]:
    if not isinstance(dataset_id, (str, int)) or isinstance(dataset_id, bool):
        raise ToolFailure("usage", "dataset_id must be the numeric dataset (Pixel) ID.")
    if agent_name is not None and not isinstance(agent_name, str):
        raise ToolFailure("usage", "agent_name must be a string when given.")
    from .live.http import LiveError, RequestRefused
    from .live.quality import read_dataset_quality

    try:
        report, _ = read_dataset_quality(str(dataset_id), agent_name, bool(strict))
    except LiveError as exc:
        raise ToolFailure(exc.kind, exc.message) from None
    except RequestRefused as exc:
        raise ToolFailure("refused", str(exc)) from None
    return report


def _run(fn: Any, *args: Any, **kwargs: Any) -> "str | CallToolResult":
    try:
        return _ok(fn(*args, **kwargs))
    except ToolFailure as exc:
        return _fail(exc.kind, exc.message)
    except Exception as exc:  # never crash the server on one bad call
        from .live.http import redact_env_token

        return _fail("internal", redact_env_token(f"{type(exc).__name__}: {exc}"))


def build_server() -> "MCPServer":
    if not MCP_AVAILABLE:
        raise RuntimeError('The MCP server needs the optional extra: pip install "capilinter[mcp]"')
    server = MCPServer("capilinter", instructions=INSTRUCTIONS, version=__version__)
    read_only = ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )
    live_read = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

    @server.tool(annotations=read_only, structured_output=False)
    def audit_payload(path: Any = None, payload_json: Any = None) -> "str | CallToolResult":
        """Check a Meta Conversions API payload offline. Pass exactly one: `path` (absolute, or ~/...) to a JSON
        file, or `payload_json` (the JSON text or object). Accepts one event, a list of events, or a {"data": [...]} body.
        Returns the CLI's JSON report (schema_version 1): per-event issues with code, severity, field, fix and
        Meta source, plus an estimated match-quality score. Reads only; sends nothing."""
        return _run(audit_payload_impl, path, payload_json)

    @server.tool(annotations=read_only, structured_output=False)
    def hash_value(field: Any = None, value: Any = None, country_code: Any = "1") -> "str | CallToolResult":
        """Normalize and SHA-256 hash one user_data value the way Meta documents. `field` is one of
        em, ph, fn, ln, ct, st, zp, country, ge, db. `country_code` is used for national phone numbers.
        Returns {field, normalized, sha256}, or a refusal when the value cannot be normalized without guessing."""
        return _run(hash_value_impl, field, value, country_code)

    @server.tool(annotations=read_only, structured_output=False)
    def list_checks(severity: Any = None, area: Any = None) -> "str | CallToolResult":
        """List CAPILinter's check codes with severity, area, title, why, fix and Meta source. Optional filters:
        severity (ERROR or WARNING) and area (required, timestamps, dedup, hashing, browser_ids, live)."""
        return _run(list_checks_impl, severity, area)

    @server.tool(annotations=read_only, structured_output=False)
    def explain_check(code: Any = None) -> "str | CallToolResult":
        """Explain one check code: why it matters, how to fix it, and the Meta documentation page to cite."""
        return _run(explain_check_impl, code)

    @server.tool(annotations=live_read, structured_output=False)
    def read_dataset_quality(
        dataset_id: Any = None, agent_name: Any = None, strict: Any = False
    ) -> "str | CallToolResult":
        """Read Meta's Dataset Quality API for a dataset (Pixel) ID, website events, read-only (GET only, enforced
        in code). Reports Meta's Event Match Quality, match-key coverage, diagnostics, event coverage, dedup-key
        coverage and data freshness per event, and flags EMQ below 6.0, Meta diagnostics, coverage below goal and
        server events missing event_id. With strict=true, flags set passed=false. Needs META_ACCESS_TOKEN in the
        server's environment. Fixture-verified."""
        return _run(read_dataset_quality_impl, dataset_id, agent_name, strict)

    return server


def main() -> None:
    try:
        server = build_server()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(2)
    server.run("stdio")


if __name__ == "__main__":
    main()
