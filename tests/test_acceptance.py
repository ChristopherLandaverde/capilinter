"""Acceptance tests for capilinter, AC1-AC8.

Written from SPEC.md before the v0.2.0 implementation. AC9 (CI) and AC10
(brand gate) are not testable here. Set CAPI_TEST_INSTALLED=1 to run the CLI
against an installed wheel instead of the repo source (this is AC7).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "fixtures"
INSTALLED = os.environ.get("CAPI_TEST_INSTALLED") == "1"


def run(args, cwd, **kw):
    env = dict(os.environ)
    if INSTALLED:
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = str(REPO)
    cmd = [sys.executable, "-m", "capilinter.cli", *args]
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, **kw)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def cli(self, *args):
        return run([str(a) for a in args], self.tmp)

    def sha(self, text):
        return hashlib.sha256(text.encode()).hexdigest()

    def test_ac1_clean_payload_passes(self):
        r = self.cli("inspect", FIX / "valid_payload.json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ac2_broken_fixtures_fail_with_named_code(self):
        cases = {
            "unhashed_pii": "RAW_PII_UNHASHED_EMAIL",
            "unhashed_phone": "RAW_PII_UNHASHED_PHONE",
            "missing_event_id": "MISSING_EVENT_ID",
        }
        for name, code in cases.items():
            with self.subTest(fixture=name):
                r = self.cli("inspect", FIX / f"{name}.json")
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(code, r.stdout + r.stderr)

    def test_ac3_bad_input_exits_2_without_traceback(self):
        binary = Path(self.tmp) / "blob.bin"
        binary.write_bytes(b"\xff\xfe\x00")
        scalar = Path(self.tmp) / "scalar.json"
        scalar.write_text("5")
        for label, target in {
            "directory": self.tmp,
            "binary": binary,
            "scalar": scalar,
        }.items():
            with self.subTest(input=label):
                r = self.cli("inspect", target)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)

    def test_ac4_hashes_match_documented_normalization(self):
        cases = [
            ("  John_Smith@gmail.com ", [], "john_smith@gmail.com"),
            ("+1 (616) 954-7888", ["--phone"], "16169547888"),
            ("Mary", ["--field", "fn"], "mary"),
            ("New York", ["--field", "ct"], "newyork"),
            ("CA", ["--field", "st"], "ca"),
            ("94035-1234", ["--field", "zp"], "94035"),
            ("US", ["--field", "country"], "us"),
            ("Female", ["--field", "ge"], "f"),
            ("1997-02-14", ["--field", "db"], "19970214"),
        ]
        for raw, flags, normalized in cases:
            with self.subTest(raw=raw, flags=flags):
                r = self.cli("hash", raw, *flags)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(self.sha(normalized), r.stdout)

    def test_ac5_strict_escalates_warnings(self):
        payload = json.loads((FIX / "valid_payload.json").read_text())
        for event in payload["data"]:
            event["event_time"] = int(time.time()) - 8 * 86400
        path = Path(self.tmp) / "stale.json"
        path.write_text(json.dumps(payload))
        self.assertEqual(self.cli("inspect", path).returncode, 0)
        self.assertEqual(self.cli("inspect", path, "--strict").returncode, 1)

    def test_ac6_json_output_is_machine_readable(self):
        r = self.cli("inspect", FIX / "unhashed_pii.json", "--json")
        report = json.loads(r.stdout)
        self.assertIs(report["passed"], False)
        codes = [i["code"] for e in report["events"] for i in e["issues"]]
        self.assertIn("RAW_PII_UNHASHED_EMAIL", codes)

    def test_ac7_runs_outside_repo(self):
        # Meaningful under CAPI_TEST_INSTALLED=1; otherwise it checks the
        # source tree works from a foreign cwd.
        r = run(
            ["--version"],
            self.tmp,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        probe = subprocess.run(
            [sys.executable, "-c", "import capilinter as m; print(m.__file__)"],
            cwd=self.tmp,
            env={k: v for k, v in os.environ.items() if INSTALLED is False or k != "PYTHONPATH"}
            | ({} if INSTALLED else {"PYTHONPATH": str(REPO)}),
            capture_output=True,
            text=True,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        mod_path = Path(probe.stdout.strip()).resolve()
        if INSTALLED:
            self.assertFalse(mod_path.is_relative_to(REPO), mod_path)
            self.test_ac1_clean_payload_passes()
            self.test_ac2_broken_fixtures_fail_with_named_code()

    def _gate(self, argv):
        if INSTALLED:
            self.skipTest("AC8 is skipped against an installed wheel")
        if shutil.which(argv[0]) is None:
            self.skipTest(f"{argv[0]} not on PATH")
        r = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_ac8_ruff_check(self):
        self._gate(["ruff", "check", "."])

    def test_ac8_ruff_format(self):
        self._gate(["ruff", "format", "--check", "."])

    def test_ac8_mypy(self):
        self._gate(["mypy"])

    def test_ac8_bandit(self):
        self._gate(["bandit", "-q", "-r", "capilinter", "-c", "pyproject.toml"])


if __name__ == "__main__":
    unittest.main()
