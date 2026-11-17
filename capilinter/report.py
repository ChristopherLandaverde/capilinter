"""Build the versioned JSON report (schema v1) shared by the CLI and the MCP server.

docs/schema/report-v1.json documents the shape. The CLI's text output is
rendered from the same dict, so every surface reports the same verdicts.
"""

import json
from pathlib import Path
from typing import Any

from .core import find_duplicate_event_ids, validate_capi_payload
from .emq import calculate_emq_score

SCHEMA_VERSION = 1


class InputError(Exception):
    """Input that cannot be audited. `kind` follows the MCP error kinds."""

    def __init__(self, message: str, kind: str = "usage") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


def load_json_file(path: Path) -> Any:
    if not path.is_file():
        raise InputError(f"Not a readable file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise InputError(f"Could not read JSON from {path}: {exc}") from None


def load_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"payload_json is not valid JSON: {exc}") from None


def extract_events(data: Any) -> list[Any] | None:
    """Return the list of events, or None if the shape is not a CAPI payload."""
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else None
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return None


def _field(event: Any, key: str) -> Any:
    return event.get(key) if isinstance(event, dict) else None


def build_report(data: Any, label: str, strict: bool = False) -> tuple[dict[str, Any], int]:
    """Return (report, exit code). Raises InputError for a non-CAPI shape.

    Exit code: 0 every event passes, 1 a check failed or there are no events.
    With strict, warnings fail too.
    """
    events = extract_events(data)
    if events is None:
        raise InputError(f'{label} is not a CAPI payload (expected an event object, a list, or {{"data": [...]}}).')
    if not events:
        return (
            {
                "schema_version": SCHEMA_VERSION,
                "file": label,
                "passed": False,
                "error": f"{label} contains no events.",
                "batch_issues": [],
                "events": [],
            },
            1,
        )

    batch_issues = find_duplicate_event_ids(events)
    failed = bool(strict and batch_issues)
    rows = []
    for idx, event in enumerate(events, 1):
        validation = validate_capi_payload(event)
        if not validation.is_valid or (strict and validation.warnings):
            failed = True
        rows.append(
            {
                "index": idx,
                "event_name": _field(event, "event_name"),
                "event_id": _field(event, "event_id"),
                "valid": validation.is_valid,
                "issues": [vars(i) for i in validation.issues],
                "emq_estimate": vars(calculate_emq_score(event)),
            }
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "file": label,
        "passed": not failed,
        "batch_issues": [vars(i) for i in batch_issues],
        "events": rows,
    }
    return report, (1 if failed else 0)
