"""Read Meta's Dataset Quality API for website events and flag what Meta's own numbers show.

Meta's values are reported as returned. Flags use registry codes:
EMQ below the 6.0 Meta recommends, Meta's EMQ diagnostics, event coverage below
Meta's goal, and server events missing the event_id dedup key.
"""

import os
from collections.abc import Mapping
from typing import Any

from .. import checks
from .http import API_VERSION, TOKEN_ENV, LiveError, get_json

SCHEMA_VERSION = 1
EMQ_RECOMMENDED = 6.0
FIELDS = "web{event_name,event_match_quality,event_coverage,dedupe_key_feedback,data_freshness}"


def _issue(code: str, message: str, field: str) -> dict[str, str]:
    check = checks.get(code)
    return {
        "severity": check.severity,
        "code": code,
        "message": message,
        "field": field,
        "fix": check.fix,
        "source": check.source,
    }


def _list(obj: Any) -> list[Any]:
    return obj if isinstance(obj, list) else []


def _pct(obj: Any) -> Any:
    return obj.get("percentage") if isinstance(obj, dict) else None


def _event(raw: Mapping[str, Any]) -> dict[str, Any]:
    emq = raw.get("event_match_quality")
    emq = emq if isinstance(emq, dict) else {}
    score = emq.get("composite_score")
    diagnostics = [
        {
            key: d.get(key)
            for key in ("name", "description", "solution", "percentage", "affected_event_count", "total_event_count")
        }
        for d in _list(emq.get("diagnostics"))
        if isinstance(d, dict)
    ]
    coverage_raw = raw.get("event_coverage")
    coverage = (
        {"percentage": coverage_raw.get("percentage"), "goal_percentage": coverage_raw.get("goal_percentage")}
        if isinstance(coverage_raw, dict)
        else None
    )
    dedupe = [
        {
            "dedupe_key": d.get("dedupe_key"),
            "browser_percentage": _pct(d.get("browser_events_with_dedupe_key")),
            "server_percentage": _pct(d.get("server_events_with_dedupe_key")),
            "overall_browser_coverage": _pct(d.get("overall_browser_coverage_from_dedupe_key")),
        }
        for d in _list(raw.get("dedupe_key_feedback"))
        if isinstance(d, dict)
    ]
    freshness_raw = raw.get("data_freshness")
    freshness = freshness_raw.get("upload_frequency") if isinstance(freshness_raw, dict) else None

    issues: list[dict[str, str]] = []
    if isinstance(score, (int, float)) and score < EMQ_RECOMMENDED:
        issues.append(
            _issue(
                "LIVE_EMQ_BELOW_RECOMMENDED",
                f"Event Match Quality is {score}/10; Meta recommends {EMQ_RECOMMENDED} or higher.",
                "event_match_quality.composite_score",
            )
        )
    for d in diagnostics:
        issues.append(
            _issue(
                "LIVE_EMQ_DIAGNOSTIC",
                f"Meta diagnostic: {d['name']} ({d['percentage']}% of events, "
                f"{d['affected_event_count']} of {d['total_event_count']}). Meta's solution: {d['solution']}",
                "event_match_quality.diagnostics",
            )
        )
    if coverage:
        pct, goal = coverage["percentage"], coverage["goal_percentage"]
        if isinstance(pct, (int, float)) and isinstance(goal, (int, float)) and pct < goal:
            issues.append(
                _issue(
                    "LIVE_EVENT_COVERAGE_BELOW_GOAL",
                    f"Event coverage is {pct}%; Meta's goal is {goal}%.",
                    "event_coverage.percentage",
                )
            )
    for d in dedupe:
        server = d["server_percentage"]
        if d["dedupe_key"] == "event_id" and isinstance(server, (int, float)) and server < 100:
            issues.append(
                _issue(
                    "LIVE_SERVER_DEDUP_KEY_LOW",
                    f"{server}% of server events carry event_id; the rest cannot be deduplicated against the pixel.",
                    "dedupe_key_feedback.server_events_with_dedupe_key",
                )
            )

    return {
        "event_name": raw.get("event_name"),
        "emq_score": score,
        "match_keys": [
            {"identifier": m.get("identifier"), "coverage": _pct(m.get("coverage"))}
            for m in _list(emq.get("match_key_feedback"))
            if isinstance(m, dict)
        ],
        "diagnostics": diagnostics,
        "event_coverage": coverage,
        "dedupe": dedupe,
        "data_freshness": freshness,
        "issues": issues,
    }


def build_live_report(raw: Any, dataset_id: str, strict: bool = False) -> tuple[dict[str, Any], int]:
    """Turn a Dataset Quality API response into the live report. Return (report, exit code)."""
    web = raw.get("web") if isinstance(raw, dict) else None
    if not isinstance(web, list):
        raise LiveError("api", "Meta's response has no 'web' events list.")
    events = [_event(e) for e in web if isinstance(e, dict)]
    flagged = any(e["issues"] for e in events)
    passed = not (strict and flagged)
    report = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "api_version": API_VERSION,
        "passed": passed,
        "events": events,
    }
    return report, (0 if passed else 1)


def read_dataset_quality(
    dataset_id: str,
    agent_name: str | None = None,
    strict: bool = False,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    """Fetch and report. Raises LiveError (usage, credentials, api, refused)."""
    env = os.environ if environ is None else environ
    dataset_id = str(dataset_id).strip()
    if not dataset_id.isdigit():
        raise LiveError("usage", f"dataset_id must be the numeric dataset (Pixel) ID, got {dataset_id!r}.")
    token = env.get(TOKEN_ENV, "").strip()
    if token and not all(33 <= ord(ch) <= 126 for ch in token):
        raise LiveError(
            "credentials",
            f"{TOKEN_ENV} contains spaces or control characters inside it. Check the value; it is not shown here.",
        )
    if not token:
        raise LiveError(
            "credentials",
            f"Set {TOKEN_ENV} to a Meta access token with access to this dataset. It is read from the environment only.",
        )
    params = {"dataset_id": dataset_id, "fields": FIELDS}
    if agent_name:
        params["agent_name"] = agent_name
    raw = get_json(params, token)
    return build_live_report(raw, dataset_id, strict)
