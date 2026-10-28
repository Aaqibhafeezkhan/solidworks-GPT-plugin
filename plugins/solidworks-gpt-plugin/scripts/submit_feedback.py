#!/usr/bin/env python3
"""Submit a validated FeedbackSubmission with bounded curl retries."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from sw_session import load_state, mark_feedback_submitted  # noqa: E402
from doctor import validate_feedback_host  # noqa: E402
from validate_feedback import (  # noqa: E402
    ValidationError,
    normalize_payload,
    read_payload,
)


DEFAULT_HOST = "https://sw-plugin.ideep.org"


def parse_response(stdout: str) -> tuple[str, str]:
    body, separator, status = stdout.rstrip().rpartition("\n")
    if not separator:
        return stdout, "000"
    return body, status.strip()


def feedback_id_from(body: str) -> str:
    try:
        response: Any = json.loads(body)
    except json.JSONDecodeError:
        return "unknown"
    if isinstance(response, dict) and response.get("id"):
        return str(response["id"])
    return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", help="Payload JSON file, or - for stdin")
    parser.add_argument("--state", type=Path, default=Path(".sw-learner-state.json"))
    parser.add_argument("--host", default=os.environ.get("SW_KB_HOST", DEFAULT_HOST))
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = normalize_payload(read_payload(args.payload))
        state = load_state(args.state)
        state_session = state.get("sessionId")
        if state_session and state_session != payload["sessionId"]:
            raise ValidationError("payload sessionId does not match local session state")

        host = args.host.rstrip("/")
        valid_host, _, host_reason = validate_feedback_host(host)
        if not valid_host:
            raise ValidationError(f"SW_KB_HOST is invalid: {host_reason}")
        if args.attempts < 1 or args.attempts > 3:
            raise ValidationError("attempts must be between 1 and 3")
        if args.dry_run:
            print("Feedback payload is valid; no network request was made.")
            return 0

        curl = shutil.which("curl")
        if not curl:
            raise OSError("curl is not available")
        # Hand curl UTF-8 bytes ourselves. In text mode subprocess would encode
        # with the locale's code page (cp1252 on most Windows machines), which
        # sends invalid JSON bytes or fails outright on characters such as "→".
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        endpoint = f"{host}/api/feedback"

        for attempt in range(args.attempts):
            try:
                completed = subprocess.run(
                    [
                        curl,
                        "--silent",
                        "--show-error",
                        "--max-time",
                        "30",
                        "--write-out",
                        "\n%{http_code}",
                        "--request",
                        "POST",
                        endpoint,
                        "--header",
                        "Content-Type: application/json",
                        "--data-binary",
                        "@-",
                    ],
                    input=body,
                    capture_output=True,
                    timeout=35,
                    check=False,
                )
                response_body, status = parse_response(
                    completed.stdout.decode("utf-8", errors="replace")
                )
            except (OSError, subprocess.SubprocessError):
                status = "000"
                response_body = ""

            if status.startswith("2"):
                feedback_id = feedback_id_from(response_body)
                try:
                    mark_feedback_submitted(args.state, feedback_id)
                except (OSError, ValueError) as exc:
                    # The server has the feedback by now. A state file that is
                    # missing or has no sessionId cannot turn that into "not
                    # submitted"; it only means the ID was not recorded.
                    if args.verbose:
                        print(
                            f"Feedback ID not recorded in {args.state}: {exc}",
                            file=sys.stderr,
                        )
                print(f"Feedback submitted. ID: {feedback_id}")
                return 0
            if status.startswith("4"):
                if args.verbose:
                    print(f"Feedback rejected with HTTP {status}", file=sys.stderr)
                return 2
            if args.verbose:
                print(
                    f"Attempt {attempt + 1} failed with HTTP {status}",
                    file=sys.stderr,
                )
            if attempt + 1 < args.attempts:
                time.sleep(args.retry_delay)
        return 3
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        if args.verbose:
            print(f"Feedback not submitted: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
