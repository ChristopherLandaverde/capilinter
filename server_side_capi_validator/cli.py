"""Command-line interface: `capi-validator inspect` and `capi-validator hash`."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from . import __version__
from .core import validate_capi_payload
from .emq import EXCELLENT, calculate_emq_score
from .hashing import normalize_and_hash_email, normalize_and_hash_phone


def _extract_events(data: Any) -> List[Any]:
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return [data]


def inspect_payload(file_path: Path, strict: bool = False, as_json: bool = False) -> int:
    """Return 0 if every event passes, 1 otherwise. --strict fails on warnings too."""
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Invalid JSON in {file_path}: {exc}", file=sys.stderr)
        return 2

    events = _extract_events(data)
    failed = False
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
            report.append({
                "index": idx,
                "event_name": event.get("event_name") if isinstance(event, dict) else None,
                "event_id": event.get("event_id") if isinstance(event, dict) else None,
                "valid": validation.is_valid,
                "issues": [vars(i) for i in validation.issues],
                "emq_estimate": vars(emq),
            })
            continue

        name = event.get("event_name", "UNKNOWN") if isinstance(event, dict) else "UNKNOWN"
        eid = event.get("event_id", "MISSING") if isinstance(event, dict) else "MISSING"
        print(f"\n[{idx}/{len(events)}] {name}  event_id={eid}")
        if validation.is_valid:
            print("  ✓ VERIFIED  schema, hashing, and dedup checks passed")
        for err in validation.errors:
            print(f"  × ERROR     {err.code}: {err.message}")
        for warn in validation.warnings:
            print(f"  ! WARNING   {warn.code}: {warn.message}")
        print(f"  Estimated match quality: {emq.score}/10.0 ({emq.grade})")
        print(f"  Matched: {', '.join(emq.matched_parameters) or 'none'}")
        if emq.score < EXCELLENT:
            for rec in emq.recommendations[:2]:
                print(f"  + {rec}")

    if as_json:
        print(json.dumps({"file": str(file_path), "passed": not failed, "events": report}, indent=2))
    else:
        print("\nResult:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="capi-validator", description="Offline Meta CAPI payload validator.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Validate a CAPI JSON file.")
    inspect_p.add_argument("file", type=Path)
    inspect_p.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    inspect_p.add_argument("--json", action="store_true", help="Print a machine-readable report.")

    hash_p = sub.add_parser("hash", help="Normalize and SHA-256 hash an email or phone.")
    hash_p.add_argument("value")
    hash_p.add_argument("--phone", action="store_true", help="Treat the value as a phone number.")
    hash_p.add_argument("--country-code", default="1", help="Default country code for 10-digit phones (default: 1).")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        sys.exit(inspect_payload(args.file, strict=args.strict, as_json=args.json))
    if args.command == "hash":
        if args.phone:
            print(normalize_and_hash_phone(args.value, args.country_code))
        else:
            print(normalize_and_hash_email(args.value))


if __name__ == "__main__":
    main()
