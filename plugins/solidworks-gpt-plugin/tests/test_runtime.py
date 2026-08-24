from __future__ import annotations

import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import doctor  # noqa: E402
from submit_feedback import parse_response  # noqa: E402
from run_checks import (  # noqa: E402
    find_source_repository_root,
    network_capable_imports,
    plugin_directory_matches_manifest,
)
from sw_session import (  # noqa: E402
    load_state,
    mark_feedback_submitted,
    mark_payload,
    read_preference,
    set_always_preference,
    start_session,
)
from validate_feedback import ValidationError, normalize_payload  # noqa: E402


class SessionStateTests(unittest.TestCase):
    def test_session_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / ".sw-learner-state.json"
            started = start_session(state_path)
            self.assertEqual(started["payloadVersion"], 0)
            self.assertTrue(started["sessionId"])

            built = mark_payload(state_path, "null", "PRJ-SHAFT-001")
            self.assertEqual(built["payloadVersion"], 1)
            self.assertIsNone(built["partId"])
            self.assertEqual(built["partNumber"], "PRJ-SHAFT-001")

            submitted = mark_feedback_submitted(state_path, "feedback-123")
            self.assertEqual(submitted["lastFeedbackId"], "feedback-123")
            self.assertEqual(load_state(state_path)["sessionId"], started["sessionId"])

    def test_preference_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preference = Path(directory) / ".sw-feedback-pref"
            self.assertEqual(read_preference(preference), "")
            set_always_preference(preference)
            self.assertEqual(read_preference(preference), "always")


class FeedbackValidationTests(unittest.TestCase):
    def test_empty_arrays_are_omitted(self) -> None:
        payload = normalize_payload(
            {
                "issues": "Built and validated a parametric shaft.",
                "sessionId": "session-1",
                "partId": None,
                "images": [],
                "macros": [],
            }
        )
        self.assertNotIn("images", payload)
        self.assertNotIn("macros", payload)

    def test_macro_requires_full_minimum_shape(self) -> None:
        with self.assertRaises(ValidationError):
            normalize_payload(
                {
                    "issues": "Built a part.",
                    "sessionId": "session-1",
                    "macros": [{"name": "build_part", "language": "python"}],
                }
            )

    def test_valid_lesson(self) -> None:
        payload = normalize_payload(
            {
                "issues": "Built and checked the component.",
                "sessionId": "session-1",
                "lessons": [
                    {
                        "category": "modeling/API",
                        "title": "Use explicit documents",
                        "whatHappened": "The active document changed.",
                        "rootCause": "An implicit ActiveDoc lookup was used.",
                        "prevention": "Pass the saved document reference to every call.",
                        "severity": "high",
                    }
                ],
            }
        )
        self.assertEqual(payload["lessons"][0]["severity"], "high")

    def test_http_status_parsing(self) -> None:
        body, status = parse_response(json.dumps({"id": "abc"}) + "\n201")
        self.assertEqual(json.loads(body)["id"], "abc")
        self.assertEqual(status, "201")


class DoctorTests(unittest.TestCase):
    def test_network_boundary_detects_from_import_aliases(self) -> None:
        source = "from urllib import request\nfrom http import client\n"
        self.assertEqual(
            ["http.client", "urllib.request"],
            network_capable_imports(source),
        )

    def test_report_is_ready_with_optional_dependency_warnings(self) -> None:
        with patch("doctor.shutil.which", return_value=None), patch(
            "doctor.detect_solidworks_registration",
            return_value=(False, "not registered in test"),
        ):
            report = doctor.build_report(doctor.PLUGIN_ROOT)

        self.assertTrue(report["ready"])
        self.assertEqual(report["network_requests"], 0)
        self.assertEqual(report["summary"]["warnings"], 2)
        self.assertEqual(report["summary"]["failures"], 0)

    def test_strict_mode_requires_curl_and_solidworks(self) -> None:
        with patch("doctor.shutil.which", return_value=None), patch(
            "doctor.detect_solidworks_registration",
            return_value=(False, "not registered in test"),
        ):
            report = doctor.build_report(doctor.PLUGIN_ROOT, strict=True)

        self.assertFalse(report["ready"])
        self.assertEqual(report["summary"]["failures"], 2)
        self.assertTrue(
            all(
                item["required"]
                for item in report["checks"]
                if item["id"] in {"curl", "solidworks"}
            )
        )

    def test_invalid_host_does_not_echo_embedded_secrets(self) -> None:
        secret_host = (
            "https://operator:do-not-print@example.com/path-secret?token=query-secret"
        )
        with patch("doctor.shutil.which", return_value="curl"), patch(
            "doctor.detect_solidworks_registration",
            return_value=(True, "registered in test"),
        ):
            report = doctor.build_report(doctor.PLUGIN_ROOT, host=secret_host)

        serialized = json.dumps(report)
        self.assertFalse(report["ready"])
        self.assertNotIn("do-not-print", serialized)
        self.assertNotIn("path-secret", serialized)
        self.assertNotIn("query-secret", serialized)
        self.assertIn("https://example.com", serialized)
        self.assertNotIn("https://example.com/", serialized)

    def test_json_cli_is_machine_readable_and_network_free(self) -> None:
        output = io.StringIO()
        with patch("doctor.shutil.which", return_value="curl"), patch(
            "doctor.detect_solidworks_registration",
            return_value=(True, "registered in test"),
        ), redirect_stdout(output):
            exit_code = doctor.main(["--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["network_requests"], 0)


class InstalledBundleValidationTests(unittest.TestCase):
    def test_source_checkout_and_installed_bundle_layouts_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_plugin = root / "source" / "plugins" / "solidworks-gpt-plugin"
            (source_plugin / ".codex-plugin").mkdir(parents=True)
            (root / "source" / ".codex-plugin").mkdir(parents=True)
            (root / "source" / ".agents" / "plugins").mkdir(parents=True)
            (root / "source" / ".codex-plugin" / "plugin.json").write_text("{}")
            (root / "source" / ".agents" / "plugins" / "marketplace.json").write_text("{}")

            installed_plugin = root / "cache" / "solidworks-gpt-plugin" / "1.0.1"
            (installed_plugin / ".codex-plugin").mkdir(parents=True)
            local_plugin = root / "local-marketplace" / "solidworks-gpt-plugin"
            (local_plugin / ".codex-plugin").mkdir(parents=True)

            self.assertEqual(find_source_repository_root(source_plugin), root / "source")
            self.assertIsNone(find_source_repository_root(installed_plugin))
            self.assertTrue(
                plugin_directory_matches_manifest(
                    source_plugin, root / "source", "solidworks-gpt-plugin", "1.0.1"
                )
            )
            self.assertTrue(
                plugin_directory_matches_manifest(
                    installed_plugin, None, "solidworks-gpt-plugin", "1.0.1"
                )
            )
            self.assertTrue(
                plugin_directory_matches_manifest(
                    local_plugin, None, "solidworks-gpt-plugin", "1.0.1"
                )
            )
            self.assertFalse(
                plugin_directory_matches_manifest(
                    installed_plugin, None, "solidworks-gpt-plugin", "2.0.0"
                )
            )


if __name__ == "__main__":
    unittest.main()
