"""Unit tests for L3 live read and the MCP tool logic. No network: urlopen is replaced."""

import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from capilinter.live import http
from capilinter.live.quality import build_live_report, read_dataset_quality
from capilinter.mcp_server import (
    ToolFailure,
    audit_payload_impl,
    explain_check_impl,
    hash_value_impl,
    list_checks_impl,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TOKEN = "synthetic-token-xyz"


class FakeResponse(io.BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def load(name: str) -> dict:
    return json.loads((FIXTURES / "live" / name).read_text())


class GuardTests(unittest.TestCase):
    def test_refuses_lookalikes(self):
        ok = "https://graph.facebook.com/v25.0/dataset_quality"
        http.check_request("GET", ok)
        for method, url in [
            ("DELETE", ok),
            ("GET", "http://graph.facebook.com/v25.0/dataset_quality"),
            ("GET", "https://graph.facebook.com:8443/v25.0/dataset_quality"),
            ("GET", "https://user:pw@graph.facebook.com/v25.0/dataset_quality"),
            ("GET", "https://graph.facebook.com.evil.example/v25.0/dataset_quality"),
            ("GET", "https://graph.facebook.com/v25.0/dataset_quality/../123/events"),
            ("GET", "https://graph.facebook.com/v19.0/dataset_quality"),
        ]:
            with self.subTest(method=method, url=url), self.assertRaises(http.RequestRefused):
                http.check_request(method, url)


class RedirectTests(unittest.TestCase):
    """urllib copies Authorization onto redirected requests; CAPILinter must never follow one."""

    def test_redirect_is_refused_before_following(self):
        import urllib.request

        handler = next(h for h in http._OPENER.handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
        req = urllib.request.Request(
            "https://graph.facebook.com/v25.0/dataset_quality?dataset_id=1",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code), self.assertRaises(http.RequestRefused) as ctx:
                handler.redirect_request(req, io.BytesIO(), code, "Moved", {}, "https://evil.example/steal")
            self.assertNotIn(TOKEN, str(ctx.exception))

    def test_redirect_surfaces_as_refused_live_error(self):
        def fake_open(request):
            raise http.RequestRefused("Redirect to https://evil.example/steal refused")

        with mock.patch.object(http, "_open", fake_open), self.assertRaises(http.RequestRefused):
            read_dataset_quality("123", environ={"META_ACCESS_TOKEN": TOKEN})


class TransportTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop(http.FIXTURE_ENV, None)

    def test_token_in_header_not_url(self):
        captured = {}

        def fake_urlopen(request):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["auth"] = request.get_header("Authorization")
            return FakeResponse(json.dumps(load("dataset_quality_healthy.json")).encode())

        with mock.patch.object(http, "_open", fake_urlopen):
            _report, code = read_dataset_quality("123", "my_agent", environ={"META_ACCESS_TOKEN": TOKEN})
        self.assertEqual(code, 0)
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["auth"], f"Bearer {TOKEN}")
        self.assertNotIn(TOKEN, captured["url"])
        self.assertIn("dataset_id=123", captured["url"])
        self.assertIn("agent_name=my_agent", captured["url"])
        self.assertTrue(captured["url"].startswith("https://graph.facebook.com/v25.0/dataset_quality?"))

    def test_http_error_body_is_reported_and_redacted(self):
        body = {"error": {"message": f"Bad token {TOKEN}", "code": 190}}

        def fake_urlopen(request):
            raise urllib.error.HTTPError(
                request.full_url, 400, "Bad Request", {}, io.BytesIO(json.dumps(body).encode())
            )

        with mock.patch.object(http, "_open", fake_urlopen), self.assertRaises(http.LiveError) as ctx:
            read_dataset_quality("123", environ={"META_ACCESS_TOKEN": TOKEN})
        self.assertEqual(ctx.exception.kind, "api")
        self.assertNotIn(TOKEN, ctx.exception.message)
        self.assertIn("code 190", ctx.exception.message)

    def test_network_failure_is_api_error(self):
        def fake_urlopen(request):
            raise urllib.error.URLError("unreachable")

        with mock.patch.object(http, "_open", fake_urlopen), self.assertRaises(http.LiveError) as ctx:
            read_dataset_quality("123", environ={"META_ACCESS_TOKEN": TOKEN})
        self.assertEqual(ctx.exception.kind, "api")

    def test_bad_dataset_id_and_missing_token(self):
        with self.assertRaises(http.LiveError) as ctx:
            read_dataset_quality("12; DROP", environ={"META_ACCESS_TOKEN": TOKEN})
        self.assertEqual(ctx.exception.kind, "usage")
        with self.assertRaises(http.LiveError) as ctx:
            read_dataset_quality("123", environ={})
        self.assertEqual(ctx.exception.kind, "credentials")


class ReportTests(unittest.TestCase):
    def test_issue_fixture_flags(self):
        report, code = build_live_report(load("dataset_quality_issues.json"), "123")
        by_name = {e["event_name"]: {i["code"] for i in e["issues"]} for e in report["events"]}
        self.assertEqual(by_name["Purchase"], {"LIVE_EMQ_BELOW_RECOMMENDED", "LIVE_EMQ_DIAGNOSTIC"})
        self.assertEqual(by_name["Lead"], {"LIVE_EVENT_COVERAGE_BELOW_GOAL"})
        self.assertEqual(by_name["AddToCart"], {"LIVE_SERVER_DEDUP_KEY_LOW"})
        self.assertEqual(code, 0)
        self.assertEqual(build_live_report(load("dataset_quality_issues.json"), "123", strict=True)[1], 1)

    def test_tolerates_partial_and_odd_responses(self):
        report, _ = build_live_report({"web": [{"event_name": "X"}, "junk"]}, "1")
        self.assertEqual(len(report["events"]), 1)
        self.assertEqual(report["events"][0]["issues"], [])
        with self.assertRaises(http.LiveError):
            build_live_report({"nope": []}, "1")


class McpToolLogicTests(unittest.TestCase):
    def test_payload_as_parsed_object(self):
        data = json.loads((FIXTURES / "valid_payload.json").read_text())
        from_obj = audit_payload_impl(payload_json=data)
        from_text = audit_payload_impl(payload_json=json.dumps(data))
        self.assertEqual(from_obj, from_text)

    def test_tool_failures(self):
        for fn, kwargs, kind in [
            (audit_payload_impl, {}, "usage"),
            (audit_payload_impl, {"path": "rel.json"}, "refused"),
            (audit_payload_impl, {"payload_json": "{not json"}, "usage"),
            (audit_payload_impl, {"payload_json": "5"}, "usage"),
            (hash_value_impl, {"field": "country", "value": "United States"}, "refused"),
            (list_checks_impl, {"severity": "fatal"}, "usage"),
            (list_checks_impl, {"area": "nope"}, "usage"),
            (explain_check_impl, {"code": "NOPE"}, "usage"),
        ]:
            with self.subTest(fn=fn.__name__, kwargs=kwargs), self.assertRaises(ToolFailure) as ctx:
                fn(**kwargs)
            self.assertEqual(ctx.exception.kind, kind)

    def test_filters(self):
        live = list_checks_impl(area="live")
        self.assertEqual(len(live), 4)
        self.assertTrue(all(c["severity"] == "ERROR" for c in list_checks_impl(severity="error")))
        self.assertEqual(explain_check_impl("missing_event_id")["code"], "MISSING_EVENT_ID")


if __name__ == "__main__":
    unittest.main()
