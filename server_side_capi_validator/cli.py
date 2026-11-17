"""Command-line interface: `capi-validator inspect` and `capi-validator hash`."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import find_duplicate_event_ids, validate_capi_payload
from .emq import EXCELLENT, calculate_emq_score
from .hashing import normalize_and_hash_field

HASHABLE_FIELDS = ("em", "ph", "fn", "ln", "ct", "st", "zp", "country", "ge", "db")


def _extract_events(data: Any) -> list[Any] | None:
    """Return the list of events, or None if the shape is not a CAPI payload."""
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else None
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return None


def _field(event: Any, key: str, default: Any) -> Any:
    return event.get(key, default) if isinstance(event, dict) else default


def inspect_payload(file_path: Path, strict: bool = False, as_json: bool = False) -> int:
    """Exit code: 0 all events pass, 1 a check failed, 2 unreadable input.

    --strict fails on warnings too.
    """
    if not file_path.is_file():
        print(f"[ERROR] Not a readable file: {file_path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        print(f"[ERROR] Could not read JSON from {file_path}: {exc}", file=sys.stderr)
        return 2

    events = _extract_events(data)
    if events is None:
        print(
            f'[ERROR] {file_path} is not a CAPI payload (expected an event object, a list, or {{"data": [...]}}).',
            file=sys.stderr,
        )
        return 2
    if not events:
        message = f"{file_path} contains no events."
        print(f"[ERROR] {message}", file=sys.stderr)
        if as_json:
            print(json.dumps({"file": str(file_path), "passed": False, "error": message, "events": []}, indent=2))
        return 1

    batch_issues = find_duplicate_event_ids(events)
    failed = bool(strict and batch_issues)
    report = []

    if not as_json:
        print("=" * 60)
        print(f"CAPI PAYLOAD RECORD: {file_path.name}  ({len(events)} event(s))")
        print("=" * 60)

    for idx, event in enumerate(events, 1):
        validation = validate_capi_payload(event)
        emq = calculate_emq_score(event)
        if not validation.is_valid or (strict and validation.warnings):
            failed = True

        if as_json:
            report.append(
                {
                    "index": idx,
                    "event_name": _field(event, "event_name", None),
                    "event_id": _field(event, "event_id", None),
                    "valid": validation.is_valid,
                    "issues": [vars(i) for i in validation.issues],
                    "emq_estimate": vars(emq),
                }
            )
            continue

        print(
            f"\n[{idx}/{len(events)}] {_field(event, 'event_name', 'UNKNOWN')}  event_id={_field(event, 'event_id', 'MISSING')}"
        )
        if validation.is_valid and not validation.warnings:
            print("  ✓ VERIFIED  schema, hashing, and dedup-key checks passed")
        elif validation.is_valid:
            count = len(validation.warnings)
            print(f"  □ OBSERVED  no errors, {count} warning{'s' if count != 1 else ''}")
        for err in validation.errors:
            print(f"  × ERROR     {err.code}: {err.message}")
        for warn in validation.warnings:
            print(f"  □ WARNING   {warn.code}: {warn.message}")
        print(f"  Estimated match quality: {emq.score}/10.0 ({emq.grade})")
        print(f"  Matched: {', '.join(emq.matched_parameters) or 'none'}")
        if emq.score < EXCELLENT:
            for rec in emq.recommendations[:2]:
                print(f"  + {rec}")

    if as_json:
        print(
            json.dumps(
                {
                    "file": str(file_path),
                    "passed": not failed,
                    "batch_issues": [vars(i) for i in batch_issues],
                    "events": report,
                },
                indent=2,
            )
        )
    else:
        for issue in batch_issues:
            print(f"\n  □ WARNING   {issue.code}: {issue.message}")
        print("\nResult:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="capi-validator", description="Offline Meta CAPI payload validator.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Validate a CAPI JSON file.")
    inspect_p.add_argument("file", type=Path)
    inspect_p.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    inspect_p.add_argument("--json", action="store_true", help="Print a machine-readable report.")

    hash_p = sub.add_parser("hash", help="Normalize and SHA-256 hash a user_data value.")
    hash_p.add_argument("value")
    group = hash_p.add_mutually_exclusive_group()
    group.add_argument("--phone", action="store_true", help="Shortcut for --field ph.")
    group.add_argument("--field", choices=HASHABLE_FIELDS, default="em", help="user_data key (default: em).")
    hash_p.add_argument("--country-code", default="1", help="Default country code for 10-digit phones (default: 1).")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        sys.exit(inspect_payload(args.file, strict=args.strict, as_json=args.json))
    if args.command == "hash":
        key = "ph" if args.phone else args.field
        try:
            print(normalize_and_hash_field(key, args.value, args.country_code))
        except ValueError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
