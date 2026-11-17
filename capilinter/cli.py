"""Command-line interface: inspect, hash, checks, explain, live quality."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__, checks
from .emq import EXCELLENT
from .hashing import normalize_and_hash_field
from .report import InputError, build_report, load_json_file

HASHABLE_FIELDS = ("em", "ph", "fn", "ln", "ct", "st", "zp", "country", "ge", "db")


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2))


def _print_inspect_text(report: dict[str, Any], name: str) -> None:
    events = report["events"]
    print("=" * 60)
    print(f"CAPI PAYLOAD RECORD: {name}  ({len(events)} event(s))")
    print("=" * 60)
    for row in events:
        event_name = row["event_name"] if row["event_name"] is not None else "UNKNOWN"
        event_id = row["event_id"] if row["event_id"] is not None else "MISSING"
        print(f"\n[{row['index']}/{len(events)}] {event_name}  event_id={event_id}")
        errors = [i for i in row["issues"] if i["severity"] == checks.ERROR]
        warnings = [i for i in row["issues"] if i["severity"] == checks.WARNING]
        if not errors and not warnings:
            print("  ✓ VERIFIED  schema, hashing, and dedup-key checks passed")
        elif not errors:
            print(f"  □ OBSERVED  no errors, {len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
        for err in errors:
            print(f"  × ERROR     {err['code']}: {err['message']}")
        for warn in warnings:
            print(f"  □ WARNING   {warn['code']}: {warn['message']}")
        emq = row["emq_estimate"]
        print(f"  Estimated match quality: {emq['score']}/10.0 ({emq['grade']})")
        print(f"  Matched: {', '.join(emq['matched_parameters']) or 'none'}")
        if emq["score"] < EXCELLENT:
            for rec in emq["recommendations"][:2]:
                print(f"  + {rec}")
    for issue in report["batch_issues"]:
        print(f"\n  □ WARNING   {issue['code']}: {issue['message']}")
    print("\nResult:", "PASS" if report["passed"] else "FAIL")


def inspect_payload(file_path: Path, strict: bool = False, as_json: bool = False) -> int:
    """Exit code: 0 all events pass, 1 a check failed or no events, 2 unreadable input.

    --strict fails on warnings too.
    """
    try:
        report, code = build_report(load_json_file(file_path), str(file_path), strict)
    except InputError as exc:
        print(f"[ERROR] {exc.message}", file=sys.stderr)
        return 2
    if "error" in report:
        print(f"[ERROR] {report['error']}", file=sys.stderr)
        if as_json:
            _print_json(report)
        return code
    if as_json:
        _print_json(report)
    else:
        _print_inspect_text(report, file_path.name)
    return code


def _checks_command(as_json: bool) -> int:
    rows = [c.to_dict() for c in checks.CHECKS.values()]
    if as_json:
        _print_json(rows)
        return 0
    for c in checks.CHECKS.values():
        print(f"{c.code:<32} {c.severity:<8} {c.area:<12} {c.title}")
    return 0


def _explain_command(code: str, as_json: bool) -> int:
    check = checks.CHECKS.get(code.strip().upper())
    if check is None:
        print(f"[ERROR] Unknown check code {code!r}. Run `capilinter checks` for the list.", file=sys.stderr)
        return 2
    if as_json:
        _print_json(check.to_dict())
        return 0
    print(f"{check.code}  ({check.severity}, {check.area})")
    print(f"{check.title}\n")
    print(f"Why it matters: {check.why}")
    print(f"How to fix it:  {check.fix}")
    print(f"Source:         {check.source} ↗")
    return 0


def _print_live_text(report: dict[str, Any]) -> None:
    print("=" * 60)
    print(f"DATASET QUALITY RECORD: dataset {report['dataset_id']}  (Meta API {report['api_version']})")
    print("=" * 60)
    for ev in report["events"]:
        print(f"\n{ev['event_name']}")
        print(f"  Event Match Quality (Meta): {ev['emq_score']}/10")
        keys = ", ".join(f"{m['identifier']} {m['coverage']}%" for m in ev["match_keys"])
        if keys:
            print(f"  Match keys: {keys}")
        if ev["event_coverage"]:
            cov = ev["event_coverage"]
            print(f"  Event coverage: {cov['percentage']}% (goal {cov['goal_percentage']}%)")
        for d in ev["dedupe"]:
            print(
                f"  Dedup key {d['dedupe_key']}: server {d['server_percentage']}%, browser {d['browser_percentage']}%"
            )
        if ev["data_freshness"]:
            print(f"  Data freshness: {ev['data_freshness']}")
        if not ev["issues"]:
            print("  ✓ VERIFIED  nothing flagged")
        for issue in ev["issues"]:
            print(f"  □ WARNING   {issue['code']}: {issue['message']}")
    print("\nResult:", "PASS" if report["passed"] else "FAIL")


def _live_quality_command(dataset_id: str, agent_name: str | None, strict: bool, as_json: bool) -> int:
    # Imported here so offline commands never load network code.
    from .live.http import LiveError, RequestRefused
    from .live.quality import read_dataset_quality

    try:
        report, code = read_dataset_quality(dataset_id, agent_name, strict)
    except LiveError as exc:
        print(f"[ERROR] {exc.message}", file=sys.stderr)
        return 2
    except RequestRefused as exc:
        print(f"[ERROR] Request refused by the read-only guard: {exc}", file=sys.stderr)
        return 2
    if as_json:
        _print_json(report)
    else:
        _print_live_text(report)
    return code


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="capilinter", description="CAPILinter: Meta CAPI payload linter.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Validate a CAPI JSON file.")
    inspect_p.add_argument("file", type=Path)
    inspect_p.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    inspect_p.add_argument("--json", action="store_true", help="Print the machine-readable report (schema v1).")

    hash_p = sub.add_parser("hash", help="Normalize and SHA-256 hash a user_data value.")
    hash_p.add_argument("value")
    group = hash_p.add_mutually_exclusive_group()
    group.add_argument("--phone", action="store_true", help="Shortcut for --field ph.")
    group.add_argument("--field", choices=HASHABLE_FIELDS, default="em", help="user_data key (default: em).")
    hash_p.add_argument("--country-code", default="1", help="Default country code for 10-digit phones (default: 1).")

    checks_p = sub.add_parser("checks", help="List every check code.")
    checks_p.add_argument("--json", action="store_true")

    explain_p = sub.add_parser("explain", help="Explain one check code: why it matters, how to fix it, Meta source.")
    explain_p.add_argument("code")
    explain_p.add_argument("--json", action="store_true")

    live_p = sub.add_parser("live", help="Read-only live checks against Meta (fixture-verified).")
    live_sub = live_p.add_subparsers(dest="live_command", required=True)
    quality_p = live_sub.add_parser(
        "quality", help="Read Meta's Dataset Quality API. Token from META_ACCESS_TOKEN, never a flag."
    )
    quality_p.add_argument("--dataset-id", required=True, help="Dataset (Pixel) ID.")
    quality_p.add_argument("--agent-name", help="Only events sent with this partner_agent value.")
    quality_p.add_argument("--strict", action="store_true", help="Treat flagged events as failures.")
    quality_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        sys.exit(inspect_payload(args.file, strict=args.strict, as_json=args.json))
    if args.command == "checks":
        sys.exit(_checks_command(args.json))
    if args.command == "explain":
        sys.exit(_explain_command(args.code, args.json))
    if args.command == "live":
        sys.exit(_live_quality_command(args.dataset_id, args.agent_name, args.strict, args.json))
    if args.command == "hash":
        key = "ph" if args.phone else args.field
        try:
            print(normalize_and_hash_field(key, args.value, args.country_code))
        except ValueError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
