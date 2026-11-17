import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from server_side_capi_validator.cli import inspect_payload, main
from server_side_capi_validator.core import find_duplicate_event_ids, is_sha256, validate_capi_payload
from server_side_capi_validator.emq import calculate_emq_score
from server_side_capi_validator.hashing import (
    normalize_and_hash_email,
    normalize_and_hash_field,
    normalize_and_hash_phone,
    normalize_field,
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



def write_tmp(tmp, name, content):
    path = Path(tmp) / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


class TestReviewRegressions(unittest.TestCase):
    """Cases found in independent review (see DECISIONS.md)."""

    def test_unhashable_action_source_is_error_not_crash(self):
        for bad in (["website"], {"a": 1}, 5):
            event = load_event("valid_payload.json")
            event["action_source"] = bad
            self.assertIn("INVALID_ACTION_SOURCE", codes(validate_capi_payload(event, now=NOW)))

    def test_unknown_action_source_is_error(self):
        event = load_event("valid_payload.json")
        event["action_source"] = "bogus"
        self.assertFalse(validate_capi_payload(event, now=NOW).is_valid)

    def test_website_requires_event_source_url(self):
        event = load_event("valid_payload.json")
        del event["event_source_url"]
        res = validate_capi_payload(event, now=NOW)
        self.assertFalse(res.is_valid)
        self.assertIn("MISSING_EVENT_SOURCE_URL", codes(res))

    def test_bad_event_time_values(self):
        for bad in (float("nan"), float("inf"), -5, 0):
            event = load_event("valid_payload.json")
            event["event_time"] = bad
            self.assertIn("INVALID_EVENT_TIME_VALUE", codes(validate_capi_payload(event, now=NOW)), bad)
        event = load_event("valid_payload.json")
        event["event_time"] = "1731600000"
        self.assertIn("INVALID_EVENT_TIME_TYPE", codes(validate_capi_payload(event, now=NOW)))

    def test_event_id_zero_is_present(self):
        event = load_event("valid_payload.json")
        event["event_id"] = 0
        self.assertNotIn("MISSING_EVENT_ID", codes(validate_capi_payload(event, now=NOW)))

    def test_duplicate_event_ids_in_batch(self):
        event = load_event("valid_payload.json")
        issues = find_duplicate_event_ids([event, dict(event), "not an event"])
        self.assertEqual([i.code for i in issues], ["DUPLICATE_EVENT_ID"])

    def test_fb_cookie_format(self):
        for bad in ("fb.", "fb.x", "fb.9.1731600000.abc", {"v": 1}):
            event = load_event("valid_payload.json")
            event["user_data"]["fbc"] = bad
            self.assertIn("MALFORMED_FBC", codes(validate_capi_payload(event, now=NOW)), bad)
            self.assertNotIn("Click ID (fbc)", calculate_emq_score(event).matched_parameters)

    def test_phone_edge_cases(self):
        self.assertEqual(normalize_phone("0044 20 7946 0958"), "442079460958")
        self.assertEqual(normalize_phone("+44 (0)20 7946 0958"), "442079460958")
        self.assertEqual(normalize_phone("５５５ ０１０ ２８３４"), "15550102834")
        self.assertEqual(normalize_phone("555-010-2834 x12"), "15550102834")
        self.assertEqual(normalize_phone("555-010-2834 ext. 12"), "15550102834")

    def test_other_field_normalization(self):
        self.assertEqual(normalize_field("fn", "  Mary-Jane "), "maryjane")
        self.assertEqual(normalize_field("ct", "San Francisco"), "sanfrancisco")
        self.assertEqual(normalize_field("st", "CA"), "ca")
        self.assertEqual(normalize_field("zp", "94103-1234"), "94103")
        self.assertEqual(normalize_field("zp", "SW1A 1AA"), "sw1a1aa")
        self.assertEqual(normalize_field("ge", "Female"), "f")
        self.assertEqual(normalize_field("db", "1990-02-14"), "19900214")
        self.assertEqual(normalize_and_hash_field("country", "US"), hashlib.sha256(b"us").hexdigest())

    def test_raw_name_points_to_repair(self):
        event = load_event("valid_payload.json")
        event["user_data"]["fn"] = "John"
        issue = next(i for i in validate_capi_payload(event, now=NOW).issues if i.code == "INVALID_SHA256")
        self.assertIn("--field fn", issue.message)

    def test_cli_rejects_empty_and_unreadable_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_inspect(write_tmp(tmp, "empty.json", {"data": []})), 1)
            self.assertEqual(run_inspect(write_tmp(tmp, "list.json", [])), 1)
            self.assertEqual(run_inspect(write_tmp(tmp, "shape.json", {"data": "x"})), 2)
            self.assertEqual(run_inspect(write_tmp(tmp, "scalar.json", "5")), 2)
            self.assertEqual(run_inspect(write_tmp(tmp, "latin1.json", b"\xff\xfe{}")), 2)
            self.assertEqual(run_inspect(Path(tmp)), 2)

    def test_cli_handles_non_object_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_tmp(tmp, "mixed.json", [load_event("valid_payload.json"), "oops", 7])
            self.assertEqual(run_inspect(path), 1)

    def test_strict_fails_on_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = load_event("valid_payload.json")
            event["event_time"] = int(__import__("time").time())
            path = write_tmp(tmp, "dupes.json", {"data": [event, event]})
            self.assertEqual(run_inspect(path), 0)
            self.assertEqual(run_inspect(path, strict=True), 1)

    def test_hash_field_cli(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["hash", "--field", "ct", "New York"])
        self.assertEqual(buf.getvalue().strip(), hashlib.sha256(b"newyork").hexdigest())


if __name__ == "__main__":
    unittest.main()
