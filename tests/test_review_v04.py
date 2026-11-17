"""Regressions from the v0.4.0 independent review (see DECISIONS.md). Written before the fixes."""

import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from capilinter import checks, cli
from capilinter.core import find_duplicate_event_ids, validate_capi_payload
from capilinter.hashing import normalize_value
from capilinter.live import http
from capilinter.live.quality import build_live_report, read_dataset_quality
from capilinter.mcp_server import (
    ToolFailure,
    audit_payload_impl,
    explain_check_impl,
    read_dataset_quality_impl,
)
from capilinter.report import MAX_EVENTS, MAX_FILE_BYTES, build_report

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SECRET = "EAAB-secret-value"
NOW = 1731600000 + 60


def valid_event() -> dict:
    return json.loads((FIXTURES / "valid_payload.json").read_text())["data"][0]


class TokenLeakTests(unittest.TestCase):
    def test_trailing_newline_token_is_stripped(self):
        seen = {}

        def fake_open(request):
            seen["auth"] = request.get_header("Authorization")
            raise http.urllib.error.URLError("offline")

        with mock.patch.object(http, "_open", fake_open), self.assertRaises(http.LiveError):
            read_dataset_quality("123", environ={"META_ACCESS_TOKEN": f"{SECRET}\n"})
        self.assertEqual(seen["auth"], f"Bearer {SECRET}")

    def test_token_with_control_characters_is_a_credentials_error(self):
        with self.assertRaises(http.LiveError) as ctx:
            read_dataset_quality("123", environ={"META_ACCESS_TOKEN": "EAAB\nsecret"})
        self.assertEqual(ctx.exception.kind, "credentials")
        self.assertNotIn("secret", ctx.exception.message)

    def test_unexpected_transport_error_is_redacted(self):
        def fake_open(request):
            raise ValueError(f"Invalid header value b'Bearer {SECRET}'")

        with mock.patch.object(http, "_open", fake_open), self.assertRaises(http.LiveError) as ctx:
            read_dataset_quality("123", environ={"META_ACCESS_TOKEN": SECRET})
        self.assertEqual(ctx.exception.kind, "api")
        self.assertNotIn(SECRET, ctx.exception.message)

    def test_mcp_internal_errors_are_redacted(self):
        from capilinter import mcp_server

        def boom(*args, **kwargs):
            raise RuntimeError(f"leaked {SECRET}")

        with mock.patch.dict("os.environ", {"META_ACCESS_TOKEN": SECRET}):
            result = mcp_server._run(boom)
        text = result.content[0].text if hasattr(result, "content") else result
        self.assertNotIn(SECRET, text)
        self.assertEqual(json.loads(text)["error"]["kind"], "internal")

    def test_cli_live_unexpected_error_exits_2_without_traceback_or_token(self):
        def boom(*args, **kwargs):
            raise RuntimeError(f"leaked {SECRET}")

        err = io.StringIO()
        with (
            mock.patch("capilinter.live.quality.read_dataset_quality", boom),
            mock.patch.dict("os.environ", {"META_ACCESS_TOKEN": SECRET}),
            contextlib.redirect_stderr(err),
            self.assertRaises(SystemExit) as ctx,
        ):
            cli.main(["live", "quality", "--dataset-id", "123"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertNotIn(SECRET, err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class InputLimitTests(unittest.TestCase):
    def test_too_many_events_refused(self):
        with self.assertRaises(Exception) as ctx:
            build_report({"data": [valid_event()] * (MAX_EVENTS + 1)}, "big")
        self.assertIn(str(MAX_EVENTS), str(ctx.exception))

    def test_oversized_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.json"
            big.write_text("[" + " " * (MAX_FILE_BYTES + 1) + "]")
            with self.assertRaises(ToolFailure) as ctx:
                audit_payload_impl(path=str(big))
            self.assertEqual(ctx.exception.kind, "usage")

    def test_bad_home_path_is_usage(self):
        with self.assertRaises(ToolFailure) as ctx:
            audit_payload_impl(path="~nosuchuser-capilinter/x.json")
        self.assertIn(ctx.exception.kind, {"usage", "refused"})

    def test_wrong_argument_types_are_tool_errors(self):
        for kwargs in ({"payload_json": 0}, {"path": 5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ToolFailure):
                audit_payload_impl(**kwargs)
        with self.assertRaises(ToolFailure):
            explain_check_impl(None)


class HashRefusalTests(unittest.TestCase):
    def test_values_that_normalize_to_nothing_are_refused(self):
        for key, raw in [("ph", "abc"), ("ph", "12"), ("em", ""), ("em", "not-an-email"), ("zp", "  "), ("fn", "123")]:
            with self.subTest(key=key, raw=raw), self.assertRaises(ValueError):
                normalize_value(key, raw)


class LiveRobustnessTests(unittest.TestCase):
    def test_odd_nested_types(self):
        raw = {
            "web": [
                {
                    "event_name": "X",
                    "event_match_quality": "oops",
                    "event_coverage": [],
                    "dedupe_key_feedback": "nope",
                    "data_freshness": 5,
                }
            ]
        }
        report, _ = build_live_report(raw, "1")
        self.assertEqual(report["events"][0]["emq_score"], None)

    def test_mcp_live_strict(self):
        with mock.patch.dict(
            "os.environ",
            {
                "META_ACCESS_TOKEN": "t",
                http.FIXTURE_ENV: str(FIXTURES / "live" / "dataset_quality_issues.json"),
            },
        ):
            self.assertTrue(read_dataset_quality_impl("123")["passed"])
            self.assertFalse(read_dataset_quality_impl("123", strict=True)["passed"])


class JsonSafetyTests(unittest.TestCase):
    def test_nan_event_id_is_reported_as_text(self):
        event = valid_event()
        event["event_id"] = math.nan
        report, _ = build_report([event], "nan")
        json.dumps(report, allow_nan=False)  # must be strict JSON


class RegistryCoverageTests(unittest.TestCase):
    """Every registered offline code is emitted by some input; every live code by the fixture."""

    def test_every_offline_code_is_triggered(self):
        base = valid_event()

        def ev(**changes):
            e = json.loads(json.dumps(base))
            for k, v in changes.items():
                if v is ...:
                    e.pop(k, None)
                else:
                    e[k] = v
            return e

        def ud(**changes):
            return ev(user_data={**base["user_data"], **changes})

        cases = [
            "not an event",
            ev(event_name=...),
            ev(event_time=...),
            ev(event_time="1731600000"),
            ev(event_time=-1),
            ev(event_time=NOW * 1000),
            ev(event_time=NOW + 3600),
            ev(event_time=NOW - 8 * 86400),
            ev(event_id=...),
            ev(action_source=...),
            ev(action_source="bogus"),
            ev(user_data=[]),
            ev(user_data={}),
            ev(event_source_url=...),
            ud(client_user_agent=None),
            ud(em=["Jane@Example.com"]),
            ud(ph=["+1 555 010 2834"]),
            ud(fn=["John"]),
            ud(em=["A" * 64]),
            ud(fbc="fb.1.123.x"),
            ud(fbp="fb.1.123.x"),
        ]
        emitted = set()
        for case in cases:
            emitted |= {i.code for i in validate_capi_payload(case, now=NOW).issues}
        emitted |= {i.code for i in find_duplicate_event_ids([base, base])}
        offline = {c for c, chk in checks.CHECKS.items() if chk.area != "live"}
        self.assertEqual(offline - emitted, set())

    def test_every_live_code_is_triggered(self):
        raw = json.loads((FIXTURES / "live" / "dataset_quality_issues.json").read_text())
        report, _ = build_live_report(raw, "1")
        emitted = {i["code"] for e in report["events"] for i in e["issues"]}
        live = {c for c, chk in checks.CHECKS.items() if chk.area == "live"}
        self.assertEqual(live - emitted, set())


if __name__ == "__main__":
    unittest.main()
