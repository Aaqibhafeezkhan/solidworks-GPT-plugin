from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import submit_feedback  # noqa: E402

HOST = "https://kb.example.test"
SESSION_ID = "session-1"


class SubmitFeedbackRetryTests(unittest.TestCase):
    """curl, PATH lookup and sleep are mocked: no network call, no real wait,
    and every file lives in a temporary directory."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.payload = Path(directory.name) / "payload.json"
        self.payload.write_text(
            json.dumps({"issues": "ok", "sessionId": SESSION_ID}), encoding="utf-8"
        )
        self.state = Path(directory.name) / "state.json"
        self.state.write_text(json.dumps({"sessionId": SESSION_ID}), encoding="utf-8")

        self.run = self.start_patch(mock.patch.object(submit_feedback.subprocess, "run"))
        self.sleep = self.start_patch(mock.patch.object(submit_feedback.time, "sleep"))
        self.start_patch(
            mock.patch.object(submit_feedback.shutil, "which", return_value="/usr/bin/curl")
        )

    def start_patch(self, patcher: mock._patch) -> mock.MagicMock:
        started = patcher.start()
        self.addCleanup(patcher.stop)
        return started

    def reply(self, stdout: bytes) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=b"")

    def run_main(self, *extra: str) -> tuple[int, str]:
        argv = [
            "submit_feedback.py",
            str(self.payload),
            "--state",
            str(self.state),
            "--host",
            HOST,
            "--retry-delay",
            "0",
            *extra,
        ]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            with contextlib.redirect_stderr(io.StringIO()):
                code = submit_feedback.main()
        return code, out.getvalue()

    def test_2xx_records_the_feedback_id_and_exits_0(self) -> None:
        self.run.return_value = self.reply(b'{"id":"feedback-123"}\n201')

        code, out = self.run_main()

        self.assertEqual(code, 0)
        self.assertIn("feedback-123", out)
        self.assertEqual(self.run.call_count, 1)
        self.sleep.assert_not_called()
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(state["lastFeedbackId"], "feedback-123")

    def test_4xx_exits_2_without_retrying(self) -> None:
        self.run.return_value = self.reply(b"problem\n400")

        code, _ = self.run_main("--attempts", "3")

        self.assertEqual(code, 2)
        self.assertEqual(self.run.call_count, 1)
        self.sleep.assert_not_called()

    def test_5xx_retries_up_to_the_attempt_limit_then_exits_3(self) -> None:
        self.run.return_value = self.reply(b"problem\n503")

        code, _ = self.run_main("--attempts", "3")

        self.assertEqual(code, 3)
        self.assertEqual(self.run.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_a_retry_that_succeeds_exits_0(self) -> None:
        self.run.side_effect = [self.reply(b"problem\n503"), self.reply(b'{"id":"feedback-9"}\n201')]

        code, _ = self.run_main("--attempts", "3")

        self.assertEqual(code, 0)
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(self.sleep.call_count, 1)

    def test_status_000_follows_the_bounded_retry_path(self) -> None:
        self.run.return_value = self.reply(b"\n000")

        code, _ = self.run_main("--attempts", "2")

        self.assertEqual(code, 3)
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(self.sleep.call_count, 1)

    def test_transport_failure_follows_the_same_bounded_retry_path(self) -> None:
        self.run.side_effect = subprocess.SubprocessError("connection reset")

        code, _ = self.run_main("--attempts", "2")

        self.assertEqual(code, 3)
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(self.sleep.call_count, 1)

    def test_invalid_host_exits_1_without_calling_curl(self) -> None:
        code, _ = self.run_main("--host", "ftp://kb.example.test")

        self.assertEqual(code, 1)
        self.run.assert_not_called()

    def test_invalid_attempt_count_exits_1_without_calling_curl(self) -> None:
        for attempts in ("0", "4"):
            with self.subTest(attempts=attempts):
                code, _ = self.run_main("--attempts", attempts)
                self.assertEqual(code, 1)
        self.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
