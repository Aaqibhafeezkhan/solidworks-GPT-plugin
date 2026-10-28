from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPT_DIR / "submit_feedback.py"
sys.path.insert(0, str(SCRIPT_DIR))
from submit_feedback import main as submit_feedback_main

# Typical CAD notes: a diameter sign, degrees, an arrow, a comparison and Persian.
ISSUES = "Hole Ø10 at 45° → fillet ≥ 2 mm; سوراخ"
FEEDBACK_ID = "fb-1"


class _RecordingHandler(BaseHTTPRequestHandler):
    received: list[bytes] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        self.received.append(self.rfile.read(length))
        body = json.dumps({"id": FEEDBACK_ID}, ensure_ascii=False).encode("utf-8")
        self.send_response(201)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _LocalServerTests(unittest.TestCase):
    """A recording KB server on a free loopback port, one per test."""

    def setUp(self) -> None:
        _RecordingHandler.received = []
        self.server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.host = f"http://127.0.0.1:{self.server.server_address[1]}"


@unittest.skipUnless(shutil.which("curl"), "curl is required")
class SubmitFeedbackEncodingTests(_LocalServerTests):
    def test_non_ascii_payload_is_sent_as_utf8_under_a_legacy_locale(self) -> None:
        payload = {"issues": ISSUES, "sessionId": "session-1"}
        with tempfile.TemporaryDirectory() as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps({"sessionId": "session-1"}), encoding="utf-8")

            # Force a non-UTF-8 locale encoding in the child: ASCII on POSIX,
            # the ANSI code page (for example cp1252) on Windows, as in real use.
            env = dict(os.environ, LC_ALL="C", PYTHONCOERCECLOCALE="0")
            env.pop("PYTHONUTF8", None)
            env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
            host = f"http://127.0.0.1:{self.server.server_address[1]}"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8=0",
                    str(SCRIPT),
                    str(payload_path),
                    "--host",
                    host,
                    "--state",
                    str(state_path),
                    "--attempts",
                    "1",
                    "--verbose",
                ],
                env=env,
                capture_output=True,
                timeout=60,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("utf-8", errors="replace"),
            )
            self.assertEqual(len(_RecordingHandler.received), 1)
            sent = json.loads(_RecordingHandler.received[0].decode("utf-8"))
            self.assertEqual(sent["issues"], ISSUES)
            stored = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["lastFeedbackId"], FEEDBACK_ID)


    def test_payload_from_stdin_is_read_as_utf8_under_a_legacy_locale(self) -> None:
        payload = {"issues": ISSUES, "sessionId": "session-1"}
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps({"sessionId": "session-1"}), encoding="utf-8")
            # PYTHONIOENCODING makes text-mode stdin non-UTF-8 on every OS,
            # including a CI runner whose locale is UTF-8.
            env = dict(os.environ, LC_ALL="C", PYTHONCOERCECLOCALE="0")
            env["PYTHONIOENCODING"] = "latin-1"
            env.pop("PYTHONUTF8", None)
            env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8=0",
                    str(SCRIPT),
                    "-",
                    "--host",
                    self.host,
                    "--state",
                    str(state_path),
                    "--attempts",
                    "1",
                ],
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                env=env,
                capture_output=True,
                timeout=60,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("utf-8", errors="replace"),
            )
            self.assertEqual(len(_RecordingHandler.received), 1)
            sent = json.loads(_RecordingHandler.received[0].decode("utf-8"))
            self.assertEqual(sent["issues"], ISSUES)

@unittest.skipUnless(shutil.which("curl"), "curl is required")
class SubmitFeedbackStateTests(_LocalServerTests):
    """Once the server has accepted the feedback, a session state that cannot
    record the ID must not turn the result into "not submitted"."""

    def submit(self, directory: str, state: dict | None) -> subprocess.CompletedProcess[bytes]:
        payload_path = Path(directory) / "payload.json"
        payload_path.write_text(
            json.dumps({"issues": "ok", "sessionId": "session-1"}), encoding="utf-8"
        )
        state_path = Path(directory) / "state.json"
        if state is not None:
            state_path.write_text(json.dumps(state), encoding="utf-8")
        env = dict(os.environ)
        env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(payload_path),
                "--host",
                self.host,
                "--state",
                str(state_path),
                "--attempts",
                "1",
                "--verbose",
            ],
            env=env,
            capture_output=True,
            timeout=60,
            check=False,
        )

    def assert_submitted(self, completed: subprocess.CompletedProcess[bytes]) -> None:
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr.decode("utf-8", errors="replace"),
        )
        self.assertIn(
            f"Feedback submitted. ID: {FEEDBACK_ID}",
            completed.stdout.decode("utf-8", errors="replace"),
        )
        self.assertEqual(len(_RecordingHandler.received), 1)

    def test_missing_state_file_is_not_reported_as_a_failed_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assert_submitted(self.submit(directory, state=None))
            self.assertFalse((Path(directory) / "state.json").exists())

    def test_state_without_session_id_is_not_reported_as_a_failed_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = self.submit(directory, state={"partId": None})
            self.assert_submitted(completed)
            self.assertIn(
                "not recorded", completed.stderr.decode("utf-8", errors="replace")
            )
            stored = json.loads((Path(directory) / "state.json").read_text(encoding="utf-8"))
            self.assertNotIn("lastFeedbackId", stored)



class SubmitFeedbackHostValidationTests(unittest.TestCase):
    def test_query_and_fragment_hosts_fail_before_transport_even_in_dry_run(self) -> None:
        payload = {"issues": "valid feedback", "sessionId": "session-1"}
        invalid_hosts = (
            "https://kb.example.test?tenant=demo",
            "https://kb.example.test#section",
        )
        with tempfile.TemporaryDirectory() as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps({"sessionId": "session-1"}), encoding="utf-8")

            for host in invalid_hosts:
                for dry_run in (False, True):
                    with self.subTest(host=host, dry_run=dry_run):
                        argv = [
                            str(SCRIPT),
                            str(payload_path),
                            "--state",
                            str(state_path),
                            "--host",
                            host,
                            "--verbose",
                        ]
                        if dry_run:
                            argv.append("--dry-run")
                        stderr = io.StringIO()
                        with patch("sys.argv", argv), \
                                patch("subprocess.run") as transport, \
                                patch("shutil.which", return_value="curl"), \
                                contextlib.redirect_stderr(stderr):
                            result = submit_feedback_main()

                        self.assertEqual(result, 1)
                        transport.assert_not_called()
                        self.assertNotIn("tenant=demo", stderr.getvalue())
                        self.assertNotIn("#section", stderr.getvalue())
                        self.assertIn("query strings and fragments", stderr.getvalue())

    def test_valid_base_path_is_preserved_by_host_validation(self) -> None:
        from doctor import validate_feedback_host

        valid, _, reason = validate_feedback_host("https://kb.example.test/tenant/api")
        self.assertTrue(valid, reason)


if __name__ == "__main__":
    unittest.main()
