from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_feedback.py"
sys.path.insert(0, str(SCRIPT.parent))
from validate_feedback import ValidationError, normalize_payload

ISSUES = "Hole Ø10 at 45° → fillet ≥ 2 mm; سوراخ"


def legacy_locale_env() -> dict[str, str]:
    # PYTHONIOENCODING makes text-mode stdin non-UTF-8 on every OS, the way
    # cp1252 does on a Windows console, even where the locale is UTF-8.
    env = dict(os.environ, LC_ALL="C", PYTHONCOERCECLOCALE="0", PYTHONIOENCODING="latin-1")
    env.pop("PYTHONUTF8", None)
    return env


class ValidateFeedbackStdinTests(unittest.TestCase):
    def run_validator(self, stdin: bytes, output: Path) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-X", "utf8=0", str(SCRIPT), "-", "--write-normalized", str(output)],
            input=stdin,
            env=legacy_locale_env(),
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_stdin_gives_the_same_text_as_a_file(self) -> None:
        payload = {"issues": ISSUES, "sessionId": "session-1"}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normalized.json"
            completed = self.run_validator(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"), output
            )
            self.assertEqual(
                completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace")
            )
            normalized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(normalized["issues"], ISSUES)

    def test_invalid_utf8_on_stdin_is_a_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "normalized.json"
            completed = self.run_validator(b'{"issues": "\xff", "sessionId": "s"}', output)
            self.assertEqual(completed.returncode, 1)
            self.assertIn(b"Invalid feedback payload", completed.stderr)
            self.assertFalse(output.exists())

    def test_explicit_null_arrays_are_rejected(self) -> None:
        base = {"issues": "issue", "sessionId": "session-1"}
        for field in ("images", "instructions", "macros", "knownErrors", "lessons"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValidationError, rf"{field} must be an array"):
                    normalize_payload({**base, field: None})

        self.assertEqual(normalize_payload(base), base)
        self.assertEqual(normalize_payload({**base, "images": []}), base)

        with tempfile.TemporaryDirectory() as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(json.dumps({**base, "images": None}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(payload_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("Invalid feedback payload: images must be an array", completed.stderr)

    def test_unsupported_image_content_type_is_rejected(self) -> None:
        base = {"issues": "issue", "sessionId": "session-1"}

        def image(content_type: str) -> dict:
            return {
                "filename": "fixture.png",
                "contentType": content_type,
                "dataBase64": "Zml4dHVyZQ==",
            }

        for content_type in (
            "image/png",
            "image/jpeg",
            "image/bmp",
            "image/tiff",
            "image/gif",
        ):
            with self.subTest(content_type=content_type):
                payload = {**base, "images": [image(content_type)]}
                self.assertEqual(normalize_payload(payload), payload)

        unsupported = {**base, "images": [image("text/plain")]}
        with self.assertRaises(ValidationError) as error:
            normalize_payload(unsupported)
        self.assertIn("images[0].contentType", str(error.exception))

        with tempfile.TemporaryDirectory() as directory:
            payload_path = Path(directory) / "payload.json"
            payload_path.write_text(json.dumps(unsupported), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), str(payload_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("Invalid feedback payload: images[0].contentType", completed.stderr)


if __name__ == "__main__":
    unittest.main()
