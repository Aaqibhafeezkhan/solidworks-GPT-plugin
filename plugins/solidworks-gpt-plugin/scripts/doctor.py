#!/usr/bin/env python3
"""Run a local, zero-network readiness check for the SolidWorks GPT Plugin."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "https://sw-plugin.ideep.org"
MINIMUM_PYTHON = (3, 9)


def result(
    check_id: str,
    status: str,
    required: bool,
    summary: str,
    **details: Any,
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "required": required,
        "summary": summary,
        "details": details,
    }


def safe_host_label(host: str) -> str:
    """Return a credential-free label suitable for diagnostics."""
    try:
        parsed = urlparse(host.strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return "<invalid>"
    if not parsed.scheme or not hostname:
        return "<invalid>"
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    authority = display_host if port is None else f"{display_host}:{port}"
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{authority}{path}"


def validate_feedback_host(host: str) -> Tuple[bool, str, str]:
    """Validate the configured base URL without connecting to it."""
    label = safe_host_label(host)
    try:
        parsed = urlparse(host.strip())
        port = parsed.port
    except ValueError as exc:
        return False, label, f"invalid port or URL: {exc}"

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False, label, "host must be an absolute HTTP(S) URL"
    if parsed.username or parsed.password:
        return False, label, "credentials are not allowed in SW_KB_HOST"
    if parsed.query or parsed.fragment:
        return False, label, "query strings and fragments are not allowed"
    if port is not None and not 1 <= port <= 65535:
        return False, label, "port must be between 1 and 65535"
    return True, label, "configuration is syntactically valid"


def check_python(version_info: Sequence[int] = sys.version_info) -> Dict[str, Any]:
    version = tuple(version_info[:3])
    passed = version[:2] >= MINIMUM_PYTHON
    return result(
        "python",
        "PASS" if passed else "FAIL",
        True,
        (
            f"Python {version[0]}.{version[1]}.{version[2]} satisfies 3.9+"
            if passed
            else f"Python {version[0]}.{version[1]}.{version[2]} is below 3.9"
        ),
        version=".".join(str(item) for item in version),
        minimum="3.9",
    )


def check_plugin_bundle(plugin_root: Path) -> Dict[str, Any]:
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be an object")
        name = str(manifest["name"])
        version = str(manifest["version"])
        skills_value = str(manifest["skills"])
        skills_path = (plugin_root / skills_value).resolve()
        skills_path.relative_to(plugin_root.resolve())
        skill_files = sorted(skills_path.glob("*/SKILL.md"))
        if name != "solidworks-gpt-plugin":
            raise ValueError(f"unexpected plugin name: {name}")
        if not version:
            raise ValueError("manifest version is empty")
        if len(skill_files) != 5:
            raise ValueError(f"expected 5 skills, found {len(skill_files)}")
        if not (plugin_root / "schemas" / "feedback-submission.schema.json").is_file():
            raise ValueError("feedback schema is missing")
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        return result(
            "plugin_bundle",
            "FAIL",
            True,
            f"Plugin bundle is invalid: {exc}",
            root=str(plugin_root),
        )

    return result(
        "plugin_bundle",
        "PASS",
        True,
        f"{name}@{version} contains its manifest, schema, and 5 skills",
        root=str(plugin_root),
        name=name,
        version=version,
        skill_count=len(skill_files),
    )


def check_feedback_host(host: str) -> Dict[str, Any]:
    valid, label, reason = validate_feedback_host(host)
    return result(
        "feedback_host",
        "PASS" if valid else "FAIL",
        True,
        (
            f"SW_KB_HOST is valid ({label}); reachability was not tested"
            if valid
            else f"SW_KB_HOST is invalid ({label}): {reason}"
        ),
        host=label,
        reachability_tested=False,
    )


def check_curl(required: bool = False) -> Dict[str, Any]:
    executable = shutil.which("curl")
    if executable:
        return result(
            "curl",
            "PASS",
            required,
            "curl is available for consent-based feedback submission",
            executable=executable,
        )
    return result(
        "curl",
        "FAIL" if required else "WARN",
        required,
        "curl is unavailable; CAD workflows still work, but feedback submission does not",
        executable=None,
    )


def detect_solidworks_registration() -> Tuple[bool, str]:
    """Inspect the local Windows COM registration without launching SolidWorks."""
    if sys.platform != "win32":
        return False, "not checked because the current platform is not Windows"
    try:
        import winreg
    except ImportError:
        return False, "the Windows registry module is unavailable"

    key_path = r"SldWorks.Application\CLSID"
    access_modes = (
        winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
        winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0),
    )
    for access in access_modes:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT,
                key_path,
                0,
                access,
            ):
                return True, "SldWorks.Application is registered"
        except OSError:
            continue
    return False, "SldWorks.Application is not registered"


def check_solidworks(required: bool = False) -> Dict[str, Any]:
    registered, detail = detect_solidworks_registration()
    if registered:
        return result(
            "solidworks",
            "PASS",
            required,
            f"{detail}; the application was not launched",
            registered=True,
            application_launched=False,
        )
    return result(
        "solidworks",
        "FAIL" if required else "WARN",
        required,
        f"{detail}; documentation and bundle checks remain available",
        registered=False,
        application_launched=False,
    )


def build_report(
    plugin_root: Path = PLUGIN_ROOT,
    host: Optional[str] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    configured_host = host if host is not None else os.environ.get(
        "SW_KB_HOST",
        DEFAULT_HOST,
    )
    checks = [
        check_python(),
        check_plugin_bundle(plugin_root.resolve()),
        check_feedback_host(configured_host),
        check_curl(required=strict),
        check_solidworks(required=strict),
    ]
    failures = [item for item in checks if item["status"] == "FAIL"]
    warnings = [item for item in checks if item["status"] == "WARN"]
    return {
        "tool": "solidworks-gpt-plugin-doctor",
        "schema_version": 1,
        "ready": not failures,
        "strict": strict,
        "network_requests": 0,
        "checks": checks,
        "summary": {
            "passed": sum(item["status"] == "PASS" for item in checks),
            "warnings": len(warnings),
            "failures": len(failures),
        },
    }


def render_human(report: Dict[str, Any]) -> str:
    lines: List[str] = ["SolidWorks GPT Plugin doctor (zero network)"]
    for item in report["checks"]:
        marker = item["status"].ljust(4)
        requirement = "required" if item["required"] else "optional"
        lines.append(f"[{marker}] {item['id']} ({requirement}): {item['summary']}")
    summary = report["summary"]
    readiness = "READY" if report["ready"] else "NOT READY"
    lines.append(
        f"{readiness}: {summary['passed']} passed, "
        f"{summary['warnings']} warnings, {summary['failures']} failures; "
        "0 network requests."
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=PLUGIN_ROOT,
        help="Installed plugin root; defaults to the bundle containing this script.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Override SW_KB_HOST for syntax validation only; no request is sent.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Require curl and a registered SolidWorks installation.",
    )
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.plugin_root, args.host, args.strict)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_human(report))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
