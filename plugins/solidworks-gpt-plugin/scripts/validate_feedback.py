#!/usr/bin/env python3
"""Validate and normalize a SolidWorks FeedbackSubmission JSON document."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ARRAY_KEYS = ("images", "instructions", "macros", "knownErrors", "lessons")
SEVERITIES = {"low", "medium", "high", "critical"}
LANGUAGES = {"python", "vba", "swapi"}


class ValidationError(ValueError):
    pass


def require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{location} must be an object")
    return value


def require_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{location} must be a non-empty string")
    return value


def validate_items(payload: dict[str, Any], key: str) -> None:
    if key not in payload:
        return
    items = payload[key]
    if not isinstance(items, list):
        raise ValidationError(f"{key} must be an array")
    if not items:
        raise ValidationError(f"{key} must be omitted when empty")

    for index, raw_item in enumerate(items):
        item = require_object(raw_item, f"{key}[{index}]")
        prefix = f"{key}[{index}]"
        if key == "images":
            require_string(item.get("filename"), f"{prefix}.filename")
            require_string(item.get("contentType"), f"{prefix}.contentType")
            require_string(item.get("dataBase64"), f"{prefix}.dataBase64")
        elif key == "instructions":
            require_string(item.get("content"), f"{prefix}.content")
        elif key == "macros":
            require_string(item.get("name"), f"{prefix}.name")
            language = require_string(item.get("language"), f"{prefix}.language")
            if language not in LANGUAGES:
                raise ValidationError(f"{prefix}.language must be one of {sorted(LANGUAGES)}")
            require_string(item.get("code"), f"{prefix}.code")
        elif key == "knownErrors":
            require_string(item.get("title"), f"{prefix}.title")
            require_string(item.get("description"), f"{prefix}.description")
            severity = item.get("severity")
            if severity is not None and severity not in SEVERITIES:
                raise ValidationError(f"{prefix}.severity must be one of {sorted(SEVERITIES)}")
        elif key == "lessons":
            for field in (
                "category",
                "title",
                "whatHappened",
                "rootCause",
                "prevention",
                "severity",
            ):
                require_string(item.get(field), f"{prefix}.{field}")
            if item["severity"] not in SEVERITIES:
                raise ValidationError(f"{prefix}.severity must be one of {sorted(SEVERITIES)}")


def normalize_payload(raw_payload: Any) -> dict[str, Any]:
    payload = deepcopy(require_object(raw_payload, "payload"))
    require_string(payload.get("issues"), "issues")
    require_string(payload.get("sessionId"), "sessionId")

    if "partId" in payload and payload["partId"] is not None:
        require_string(payload["partId"], "partId")

    for key in ARRAY_KEYS:
        if key in payload and payload[key] == []:
            payload.pop(key)
        validate_items(payload, key)
    return payload


def read_payload(path: str) -> Any:
    if path == "-":
        # Read bytes: text-mode stdin decodes with the locale code page (cp1252
        # on Windows), which garbles UTF-8 input. json.loads detects UTF-8/16/32.
        return json.loads(sys.stdin.buffer.read())
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", help="Payload JSON file, or - for stdin")
    parser.add_argument(
        "--write-normalized",
        type=Path,
        help="Write the normalized payload to this private local path",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = normalize_payload(read_payload(args.payload))
        if args.write_normalized:
            args.write_normalized.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print("Feedback payload is valid.")
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Invalid feedback payload: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
