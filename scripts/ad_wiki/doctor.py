from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import ADWikiError, PLUGIN_VERSION, validate_repository


REQUIRED_SKILLS = ("ad-wiki-maintainer", "ad-wiki-query")
REQUIRED_SCRIPTS = (
    "apply_run.py",
    "approve_run.py",
    "build_index.py",
    "doctor_plugin.py",
    "init_bundle.py",
    "migrate_bundle.py",
    "prepare_run.py",
    "query_registered_raw.py",
    "raw_diff_guard.py",
    "register_source.py",
    "review_run.py",
    "validate_bundle.py",
    "write_run_report.py",
)


def _read_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        errors.append(f"missing or unsafe file: {path.name}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {path.name}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"JSON root must be an object: {path.name}")
        return None
    return value


def inspect_plugin(
    plugin_root: str | Path,
    *,
    repo: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(plugin_root).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if not root.is_dir():
        return {
            "errors": ["plugin root is not a directory"],
            "ready": False,
            "status": "not-ready",
            "warnings": [],
        }

    manifests = {
        "codex": _read_json(root / ".codex-plugin/plugin.json", errors),
        "claude": _read_json(root / ".claude-plugin/plugin.json", errors),
    }
    marketplaces = {
        "codex": _read_json(root / ".agents/plugins/marketplace.json", errors),
        "claude": _read_json(root / ".claude-plugin/marketplace.json", errors),
    }
    for host, manifest in manifests.items():
        if manifest is None:
            continue
        if manifest.get("name") != "ad-wiki":
            errors.append(f"{host} manifest name must be ad-wiki")
        if manifest.get("version") != PLUGIN_VERSION:
            errors.append(f"{host} manifest version must be {PLUGIN_VERSION}")
        if manifest.get("skills") != "./skills/":
            errors.append(f"{host} manifest skills must be ./skills/")
    for host, marketplace in marketplaces.items():
        if marketplace is None:
            continue
        if marketplace.get("name") != "ad-wiki-team":
            errors.append(f"{host} marketplace name must be ad-wiki-team")
        plugins = marketplace.get("plugins")
        if not isinstance(plugins, list) or len(plugins) != 1 or plugins[0].get("name") != "ad-wiki":
            errors.append(f"{host} marketplace must contain exactly one ad-wiki plugin")
            continue
        source = plugins[0].get("source")
        expected_source = {"source": "local", "path": "./"} if host == "codex" else "./"
        if source != expected_source:
            errors.append(f"{host} marketplace must resolve ad-wiki from ./")

    for skill in REQUIRED_SKILLS:
        if not (root / "skills" / skill / "SKILL.md").is_file():
            errors.append(f"missing packaged Skill: {skill}")
    for script in REQUIRED_SCRIPTS:
        if not (root / "scripts" / script).is_file():
            errors.append(f"missing packaged command: {script}")
    if not (root / "scripts/ad_wiki/core.py").is_file():
        errors.append("missing canonical Runtime core")

    repository_report: dict[str, Any] | None = None
    if repo is not None:
        try:
            repository_report = validate_repository(repo)
        except (ADWikiError, OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"target AD Wiki could not be validated: {exc}")
        else:
            if not repository_report["ok"]:
                errors.append("target AD Wiki failed validation")
            if repository_report["warnings"]:
                warnings.append("target AD Wiki has reviewable validation warnings")

    return {
        "errors": errors,
        "hosts": {
            host: {
                "manifest": manifest is not None,
                "marketplace": marketplaces[host] is not None,
            }
            for host, manifest in manifests.items()
        },
        "limits": ["package readiness does not prove host installation or runtime discovery"],
        "plugin_version": PLUGIN_VERSION,
        "ready": not errors,
        "repository": repository_report,
        "status": "ready" if not errors else "not-ready",
        "warnings": warnings,
    }
