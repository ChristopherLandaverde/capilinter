import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from server_side_capi_validator.cli import inspect_payload, main
from server_side_capi_validator.core import is_sha256, validate_capi_payload
from server_side_capi_validator.emq import calculate_emq_score
from server_side_capi_validator.hashing import (
    normalize_and_hash_email,
    normalize_and_hash_phone,
    normalize_phone,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
NOW = 1731600000 + 60  # one minute after the fixture timestamps
SHA_FOO = "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"


def load_event(name):
    return json.loads((FIXTURES / name).read_text())["data"][0]


def codes(result):
    return {i.code for i in result.issues}


def run_inspect(path, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return inspect_payload(path, **kwargs)


class TestHashing(unittest.TestCase):
    def test_sha256_detection(self):
        self.assertTrue(is_sha256(SHA_FOO))
        self.assertFalse(is_sha256(SHA_FOO.upper()))
        self.assertFalse(is_sha256("user@example.com"))
        self.assertFalse(is_sha256(None))

    def test_email_normalization(self):
        self.assertEqual(
            normalize_and_hash_email("  Test.User@Example.COM  "),
            hashlib.sha256(b"test.user@example.com").hexdigest(),
        )

    def test_phone_normalization_has_no_plus(self):
        self.assertEqual(normalize_phone("(555) 010-2834"), "15550102834")
        self.assertEqual(normalize_phone("+44 20 7946 0958"), "442079460958")
        self.assertEqual(
            normalize_and_hash_phone("+1 (555) 010-2834"),
            hashlib.sha256(b"15550102834").hexdigest(),
        )


class TestValidation(unittest.TestCase):
    def test_valid_fixture_passes(self):
        res = validate_capi_payload(load_event("valid_payload.json"), now=NOW)
        self.assertTrue(res.is_valid, res.issues)
        self.assertEqual(res.issues, [])

    def test_raw_email_flagged(self):
        res = validate_capi_payload(load_event("unhashed_pii.json"), now=NOW)
        self.assertFalse(res.is_valid)
        self.assertIn("RAW_PII_UNHASHED_EMAIL", codes(res))

    def test_raw_phone_flagged(self):
        res = validate_capi_payload(load_event("unhashed_phone.json"), now=NOW)
        self.assertFalse(res.is_valid)
        self.assertIn("RAW_PII_UNHASHED_PHONE", codes(res))

    def test_missing_event_id_fails(self):
        res = validate_capi_payload(load_event("missing_event_id.json"), now=NOW)
        self.assertFalse(res.is_valid)
        self.assertIn("MISSING_EVENT_ID", codes(res))

    def test_uppercase_hash_is_warning(self):
        event = load_event("valid_payload.json")
        event["user_data"]["em"] = [SHA_FOO.upper()]
        res = validate_capi_payload(event, now=NOW)
        self.assertTrue(res.is_valid)
        self.assertIn("HASH_NOT_LOWERCASE", codes(res))

    def test_event_time_checks(self):
        event = load_event("valid_payload.json")
        event["event_time"] = NOW * 1000
        self.assertIn("EVENT_TIME_IN_MILLISECONDS", codes(validate_capi_payload(event, now=NOW)))
        event["event_time"] = NOW + 3600
        self.assertIn("EVENT_TIME_IN_FUTURE", codes(validate_capi_payload(event, now=NOW)))
        event["event_time"] = NOW - 8 * 86400
        res = validate_capi_payload(event, now=NOW)
        self.assertTrue(res.is_valid)
        self.assertIn("EVENT_TIME_STALE", codes(res))

    def test_website_requires_user_agent(self):
        event = load_event("valid_payload.json")
        del event["user_data"]["client_user_agent"]
        self.assertIn("MISSING_CLIENT_USER_AGENT", codes(validate_capi_payload(event, now=NOW)))

    def test_non_dict_inputs(self):
        self.assertFalse(validate_capi_payload("nope").is_valid)
        res = validate_capi_payload({"event_name": "Lead", "user_data": []}, now=NOW)
        self.assertIn("INVALID_USER_DATA", codes(res))


class TestEMQ(unittest.TestCase):
    def test_full_payload_scores_excellent(self):
        report = calculate_emq_score(load_event("valid_payload.json"))
        self.assertEqual(report.score, 10.0)
        self.assertEqual(report.grade, "EXCELLENT")
        self.assertEqual(report.missing_parameters, [])

    def test_unhashed_email_earns_no_credit(self):
        report = calculate_emq_score(load_event("unhashed_pii.json"))
        self.assertNotIn("Hashed email (em)", report.matched_parameters)
        self.assertEqual(report.score, 1.0)
        self.assertEqual(report.grade, "POOR")


class TestCLI(unittest.TestCase):
    def test_exit_codes(self):
        self.assertEqual(run_inspect(FIXTURES / "valid_payload.json"), 0)
        self.assertEqual(run_inspect(FIXTURES / "unhashed_pii.json"), 1)
        self.assertEqual(run_inspect(FIXTURES / "missing_event_id.json"), 1)
        self.assertEqual(run_inspect(FIXTURES / "does_not_exist.json"), 2)

    def test_strict_fails_on_stale_warning(self):
        # Fixture timestamps are older than 7 days relative to the real clock.
        self.assertEqual(run_inspect(FIXTURES / "valid_payload.json", strict=True), 1)

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json")
            self.assertEqual(run_inspect(bad), 2)

    def test_json_report(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_code = inspect_payload(FIXTURES / "unhashed_pii.json", as_json=True)
        report = json.loads(buf.getvalue())
        self.assertEqual(run_code, 1)
        self.assertFalse(report["passed"])
        self.assertIn("RAW_PII_UNHASHED_EMAIL", {i["code"] for i in report["events"][0]["issues"]})

    def test_hash_command(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["hash", "  Jane.Doe@Example.com "])
        self.assertEqual(buf.getvalue().strip(), hashlib.sha256(b"jane.doe@example.com").hexdigest())


if __name__ == "__main__":
    unittest.main()
