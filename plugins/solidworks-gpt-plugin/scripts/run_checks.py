#!/usr/bin/env python3
"""Run self-contained structural and runtime checks for the plugin."""

from __future__ import annotations

import ast
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def find_source_repository_root(plugin_root: Path) -> Optional[Path]:
    """Return the source checkout root, or None for an installed plugin bundle."""
    candidate = plugin_root.parents[1]
    if (
        (candidate / ".codex-plugin" / "plugin.json").is_file()
        and (candidate / ".agents" / "plugins" / "marketplace.json").is_file()
    ):
        return candidate
    return None


REPOSITORY_ROOT = find_source_repository_root(PLUGIN_ROOT)


def plugin_directory_matches_manifest(
    plugin_root: Path,
    repository_root: Optional[Path],
    name: str,
    version: str,
) -> bool:
    """Accept source, flat local-marketplace, and versioned-cache layouts."""
    if repository_root is not None or plugin_root.name == name:
        return plugin_root.name == name
    return plugin_root.parent.name == name and plugin_root.name == version


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def check_manifest() -> None:
    plugin_manifest_path = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
    manifest = load_json(plugin_manifest_path)
    for key in ("version", "description", "author", "skills", "interface"):
        if not manifest.get(key):
            raise ValueError(f"Plugin manifest is missing {key}")
    if not plugin_directory_matches_manifest(
        PLUGIN_ROOT,
        REPOSITORY_ROOT,
        str(manifest.get("name", "")),
        str(manifest["version"]),
    ):
        raise ValueError("Plugin cache/source path does not match manifest name and version")

    manifests = [(plugin_manifest_path, manifest)]
    if REPOSITORY_ROOT is not None:
        root_manifest_path = REPOSITORY_ROOT / ".codex-plugin" / "plugin.json"
        root_manifest = load_json(root_manifest_path)
        for key in ("name", "version", "description", "author", "repository", "license"):
            if root_manifest.get(key) != manifest.get(key):
                raise ValueError(f"Root and bundled manifests disagree on {key}")
        if root_manifest.get("skills") != "./plugins/solidworks-gpt-plugin/skills/":
            raise ValueError("Root manifest skills path does not target the bundled plugin")
        manifests.append((root_manifest_path, root_manifest))

    for path, value in manifests:
        icon = value.get("interface", {}).get("composerIcon")
        if not icon:
            raise ValueError(f"Plugin manifest is missing interface.composerIcon: {path}")
        icon_path = (path.parent.parent / icon).resolve()
        if not icon_path.is_file() or icon_path.suffix.lower() not in {".svg", ".png"}:
            raise ValueError(f"Plugin icon is missing or unsupported: {icon_path}")

    if REPOSITORY_ROOT is not None:
        marketplace = load_json(
            REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json"
        )
        entries = marketplace.get("plugins") or []
        matching = [entry for entry in entries if entry.get("name") == manifest["name"]]
        if len(matching) != 1:
            raise ValueError("Marketplace must contain exactly one plugin entry")
        if matching[0].get("source", {}).get("path") != f"./plugins/{PLUGIN_ROOT.name}":
            raise ValueError("Marketplace source.path does not match plugin location")


def check_repository_security() -> None:
    for filename in ("README.md", "SECURITY.md", "LICENSE", "requirements-lock.txt"):
        if not (PLUGIN_ROOT / filename).is_file():
            raise ValueError(f"Installable plugin bundle must include {filename}")

    plugin_icon = PLUGIN_ROOT / "assets" / "icon.svg"
    if not plugin_icon.is_file():
        raise ValueError("Installable plugin bundle must include assets/icon.svg")
    if plugin_icon.stat().st_size > 50_000:
        raise ValueError("Plugin icon must remain under 50 KB")

    if REPOSITORY_ROOT is not None:
        if not (REPOSITORY_ROOT / "SECURITY.md").is_file():
            raise ValueError("Repository must include SECURITY.md")
        root_icon = REPOSITORY_ROOT / "assets" / "icon.svg"
        if root_icon.read_bytes() != plugin_icon.read_bytes():
            raise ValueError("Root and bundled plugin icons must stay identical")

        action_pattern = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
        sha_pattern = re.compile(r"^[^@]+@[0-9a-f]{40}$")
        for workflow in sorted((REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml")):
            for action in action_pattern.findall(workflow.read_text(encoding="utf-8")):
                if action.startswith("./"):
                    continue
                if not sha_pattern.fullmatch(action):
                    raise ValueError(f"GitHub Action must be SHA-pinned: {workflow}: {action}")


def check_skills() -> None:
    skill_files = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
    if len(skill_files) != 5:
        raise ValueError(f"Expected 5 skills, found {len(skill_files)}")
    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        if "[TODO:" in text:
            raise ValueError(f"Unresolved TODO in {path}")
        if not text.startswith("---\nname: "):
            raise ValueError(f"Invalid skill frontmatter in {path}")
        if f"name: {path.parent.name}\n" not in text:
            raise ValueError(f"Skill name does not match folder: {path}")


def check_python() -> None:
    scripts = sorted((PLUGIN_ROOT / "scripts").glob("*.py"))
    for script in scripts:
        py_compile.compile(str(script), doraise=True)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(PLUGIN_ROOT / "tests"),
            "-v",
        ],
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.returncode)


def network_capable_imports(source: str, filename: str = "<doctor>") -> list[str]:
    """Return forbidden imports, including ``from package import module`` forms."""
    tree = ast.parse(source, filename=filename)
    forbidden = {
        "aiohttp",
        "http.client",
        "requests",
        "socket",
        "subprocess",
        "urllib.request",
        "urllib3",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(
                f"{module}.{alias.name}" if module else alias.name
                for alias in node.names
            )
    return sorted(imported & forbidden)


def check_doctor_network_boundary() -> None:
    """Keep the installation doctor statically free of network-capable modules."""
    doctor_path = PLUGIN_ROOT / "scripts" / "doctor.py"
    violations = network_capable_imports(
        doctor_path.read_text(encoding="utf-8"),
        str(doctor_path),
    )
    if violations:
        raise ValueError(
            "Installation doctor must remain zero-network; forbidden imports: "
            + ", ".join(violations)
        )


def main() -> int:
    check_manifest()
    check_skills()
    check_repository_security()
    check_doctor_network_boundary()
    load_json(PLUGIN_ROOT / "schemas" / "feedback-submission.schema.json")
    check_python()
    layout = "source checkout" if REPOSITORY_ROOT is not None else "installed bundle"
    print(f"All plugin checks passed ({layout}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
