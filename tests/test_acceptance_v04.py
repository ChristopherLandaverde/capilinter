"""Acceptance tests for CAPILinter v0.4.0 (AC1-AC8, AC12, AC13).

Written from SPEC.md and the PLAN.md interface contract BEFORE the
implementation exists. Set CAPI_TEST_INSTALLED=1 to run against an installed
wheel instead of the repo source. MCP tests need the `mcp` SDK; schema tests
need `jsonschema`; both skip if missing.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "fixtures"
LIVE = FIX / "live"
INSTALLED = os.environ.get("CAPI_TEST_INSTALLED") == "1"
TOKEN = "synthetic-token-123"
FB = "https://developers.facebook.com/"
PAYLOADS = sorted(FIX.glob("*.json"))

try:
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    HAVE_MCP = True
except Exception:  # pragma: no cover
    HAVE_MCP = False


def base_env(**extra):
    env = dict(os.environ)
    env.pop("META_ACCESS_TOKEN", None)
    env.pop("CAPILINTER_LIVE_FIXTURE", None)
    if INSTALLED:
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = str(REPO)
    env.update(extra)
    return env


def cli(*args, env=None):
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, "-m", "capilinter.cli", *map(str, args)],
            cwd=tmp,
            env=env or base_env(),
            capture_output=True,
            text=True,
        )


def mcp_session(calls, env=None, list_tools=False):
    """Open one stdio session, run [(tool, args)...]; return (tools, results)."""
    if not HAVE_MCP:
        raise unittest.SkipTest("mcp SDK not installed")
    params = StdioServerParameters(command=sys.executable, args=["-m", "capilinter.mcp_server"], env=env or base_env())

    async def go():
        out = []
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools if list_tools else None
            for name, args in calls:
                res = await s.call_tool(name, args)
                out.append(res)
        return tools, out

    return anyio.run(go)


def body(res):
    return json.loads(res.content[0].text)


def is_err(res):
    return bool(getattr(res, "is_error", getattr(res, "isError", False)))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        from capilinter.checks import CHECKS

        self.CHECKS = CHECKS

    def test_ac1_emitted_codes_are_registered(self):
        pat = re.compile(r'"([A-Z][A-Z0-9_]{5,})"')
        for rel in ("capilinter/core.py", "capilinter/live/quality.py"):
            src = (REPO / rel).read_text()
            for code in set(pat.findall(src)):
                self.assertIn(code, self.CHECKS, f"{code} in {rel} not in CHECKS")

    def test_ac1_codes_documented_in_meta_rules(self):
        doc = (REPO / "docs" / "meta-rules.md").read_text()
        for code in self.CHECKS:
            self.assertIn(code, doc)

    def test_ac1_entries_complete(self):
        self.assertTrue(self.CHECKS)
        for code, c in self.CHECKS.items():
            self.assertTrue(c.why.strip(), code)
            self.assertTrue(c.fix.strip(), code)
            self.assertTrue(c.source.startswith(FB), code)


class CliTests(unittest.TestCase):
    def test_ac2_json_validates_against_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads((REPO / "docs/schema/report-v1.json").read_text())
        for f in PAYLOADS:
            with self.subTest(fixture=f.name):
                r = cli("inspect", f, "--json")
                self.assertIn(r.returncode, (0, 1), r.stderr)
                rep = json.loads(r.stdout)
                jsonschema.validate(rep, schema)
                self.assertEqual(rep["schema_version"], 1)
                for ev in rep["events"]:
                    for i in ev["issues"]:
                        self.assertTrue(i["fix"])
                        self.assertTrue(i["source"])

    def test_ac3_checks_lists_registry(self):
        from capilinter.checks import CHECKS

        r = cli("checks", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual({c["code"] for c in json.loads(r.stdout)}, set(CHECKS))

    def test_ac3_explain(self):
        r = cli("explain", "MISSING_EVENT_ID", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(d["why"].strip())
        self.assertTrue(d["fix"].strip())
        self.assertTrue(d["source"].startswith(FB))

    def test_ac3_explain_unknown_exits_2(self):
        self.assertEqual(cli("explain", "NOPE").returncode, 2)


class McpOfflineTests(unittest.TestCase):
    def test_ac4_exactly_five_read_only_tools(self):
        tools, _ = mcp_session([], list_tools=True)
        self.assertEqual(
            {t.name for t in tools},
            {"audit_payload", "hash_value", "list_checks", "explain_check", "read_dataset_quality"},
        )
        for t in tools:
            self.assertIs(t.annotations.read_only_hint, True, t.name)

    def test_ac5_audit_equals_cli(self):
        calls = [("audit_payload", {"path": str(f)}) for f in PAYLOADS]
        calls += [("audit_payload", {"payload_json": f.read_text()}) for f in PAYLOADS]
        _, res = mcp_session(calls)
        n = len(PAYLOADS)
        for i, f in enumerate(PAYLOADS):
            cli_rep = json.loads(cli("inspect", f, "--json").stdout)
            cli_rep.pop("file", None)
            with self.subTest(fixture=f.name):
                by_path = body(res[i])
                by_path.pop("file", None)
                self.assertEqual(by_path, cli_rep)
                by_text = body(res[n + i])
                self.assertEqual(by_text["events"], cli_rep["events"])
                self.assertEqual(by_text["passed"], cli_rep["passed"])

    def test_ac5_hash_equals_cli(self):
        raw = "  John_Smith@gmail.com "
        _, res = mcp_session([("hash_value", {"field": "em", "value": raw})])
        d = body(res[0])
        self.assertEqual(d["normalized"], "john_smith@gmail.com")
        self.assertEqual(d["sha256"], hashlib.sha256(b"john_smith@gmail.com").hexdigest())
        r = cli("hash", raw)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(d["sha256"], r.stdout)

    def test_ac6_bad_input_is_tool_error_and_server_survives(self):
        good = str(FIX / "valid_payload.json")
        calls = [
            ("audit_payload", {"path": "fixtures/valid_payload.json"}),
            ("audit_payload", {"path": "/nonexistent/nope.json"}),
            ("audit_payload", {"path": good, "payload_json": "{}"}),
            ("audit_payload", {}),
            ("hash_value", {"field": "zz", "value": "x"}),
            ("audit_payload", {"path": good}),
        ]
        _, res = mcp_session(calls)
        for r in res[:5]:
            self.assertTrue(is_err(r))
            self.assertIn(body(r)["error"]["kind"], {"usage", "refused"})
        self.assertFalse(is_err(res[5]))
        self.assertIn("events", body(res[5]))


class OfflineNetworkTests(unittest.TestCase):
    def test_ac7_offline_flows_work_with_sockets_disabled(self):
        script = (
            "import socket, sys\n"
            "def _boom(*a, **k): raise RuntimeError('network disabled')\n"
            "socket.socket = _boom\n"
            "socket.create_connection = _boom\n"
            "socket.getaddrinfo = _boom\n"
            "from capilinter import cli\n"
            "fx = sys.argv[1]\n"
            "runs = [['inspect', fx + '/valid_payload.json'],\n"
            "        ['hash', 'a@b.com'], ['checks'], ['explain', 'MISSING_EVENT_ID']]\n"
            "for a in runs:\n"
            "    try:\n"
            "        rc = cli.main(a)\n"
            "    except SystemExit as e:\n"
            "        rc = e.code or 0\n"
            "    assert rc in (0, None), (a, rc)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, "-c", script, str(FIX)], cwd=tmp, env=base_env(), capture_output=True, text=True
            )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ac7_only_live_http_imports_network_libs(self):
        banned = ("import urllib", "from urllib", "http.client", "import socket")
        for p in (REPO / "capilinter").rglob("*.py"):
            if p.relative_to(REPO).as_posix() == "capilinter/live/http.py":
                continue
            text = p.read_text()
            for b in banned:
                self.assertNotIn(b, text, f"{p} contains {b!r}")


class LiveTests(unittest.TestCase):
    def live_env(self, fixture, **extra):
        return base_env(META_ACCESS_TOKEN=TOKEN, CAPILINTER_LIVE_FIXTURE=str(LIVE / fixture), **extra)

    def quality(self, fixture, *flags):
        return cli("live", "quality", "--dataset-id", "123", "--json", *flags, env=self.live_env(fixture))

    def test_ac12_issues_fixture(self):
        r = self.quality("dataset_quality_issues.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = json.loads(r.stdout)
        self.assertEqual(rep["schema_version"], 1)
        self.assertEqual(rep["api_version"], "v25.0")
        ev = {e["event_name"]: e for e in rep["events"]}
        codes = lambda n: {i["code"] for i in ev[n]["issues"]}  # noqa: E731
        self.assertEqual(ev["Purchase"]["emq_score"], 4.7)
        self.assertIn("LIVE_EMQ_BELOW_RECOMMENDED", codes("Purchase"))
        self.assertIn("LIVE_EMQ_DIAGNOSTIC", codes("Purchase"))
        self.assertIn("LIVE_EVENT_COVERAGE_BELOW_GOAL", codes("Lead"))
        self.assertIn("LIVE_SERVER_DEDUP_KEY_LOW", codes("AddToCart"))
        self.assertEqual(self.quality("dataset_quality_issues.json", "--strict").returncode, 1)

    def test_ac12_healthy_fixture(self):
        for flags in ((), ("--strict",)):
            r = self.quality("dataset_quality_healthy.json", *flags)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for e in json.loads(r.stdout)["events"]:
                self.assertEqual(e["issues"], [])

    def test_ac12_mcp_equals_cli(self):
        cli_rep = json.loads(self.quality("dataset_quality_issues.json").stdout)
        _, res = mcp_session(
            [("read_dataset_quality", {"dataset_id": "123"})],
            env=self.live_env("dataset_quality_issues.json"),
        )
        self.assertFalse(is_err(res[0]), res[0].content[0].text)
        self.assertEqual(body(res[0]), cli_rep)
        self.assertNotIn(TOKEN, res[0].content[0].text)

    def test_ac13_missing_token(self):
        env = base_env(CAPILINTER_LIVE_FIXTURE=str(LIVE / "dataset_quality_issues.json"))
        r = cli("live", "quality", "--dataset-id", "123", "--json", env=env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        _, res = mcp_session([("read_dataset_quality", {"dataset_id": "123"})], env=env)
        self.assertTrue(is_err(res[0]))
        self.assertEqual(body(res[0])["error"]["kind"], "credentials")

    def test_ac13_api_error_and_token_never_leaks(self):
        r = self.quality("api_error_invalid_token.json")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Invalid OAuth", r.stdout + r.stderr)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)
        _, res = mcp_session(
            [("read_dataset_quality", {"dataset_id": "123"})],
            env=self.live_env("api_error_invalid_token.json"),
        )
        self.assertTrue(is_err(res[0]))
        d = body(res[0])["error"]
        self.assertEqual(d["kind"], "api")
        self.assertIn("Invalid OAuth", d["message"])
        self.assertNotIn(TOKEN, res[0].content[0].text)

    def test_ac13_guard_refuses_bad_requests(self):
        from capilinter.live import http

        guard = getattr(http, "check_request", None) or getattr(http, "guard_request", None)
        self.assertTrue(callable(guard), "live/http.py needs check_request or guard_request")
        ok = "https://graph.facebook.com/v25.0/dataset_quality"
        bad = [
            ("POST", ok),
            ("GET", "https://evil.example.com/v25.0/dataset_quality"),
            ("GET", "https://graph.facebook.com/v25.0/123/events"),
        ]
        for method, url in bad:
            with self.subTest(method=method, url=url), self.assertRaises(http.RequestRefused):
                guard(method, url)
        guard("GET", ok)  # the one allowed request passes


class PackagingTests(unittest.TestCase):
    @unittest.skipUnless(INSTALLED, "AC8 needs CAPI_TEST_INSTALLED=1")
    def test_ac8_core_has_no_runtime_deps(self):
        from importlib.metadata import requires

        reqs = requires("capilinter") or []
        for r in reqs:
            self.assertIn("extra ==", r, f"runtime dependency: {r}")
        mcp_reqs = [r for r in reqs if re.split(r"[\s\[<>=!~;]", r, maxsplit=1)[0].lower() == "mcp"]
        self.assertTrue(mcp_reqs, "the mcp extra should require the mcp package")
        for r in mcp_reqs:
            self.assertRegex(r, r"extra\s*==\s*['\"]mcp['\"]")


if __name__ == "__main__":
    unittest.main()
