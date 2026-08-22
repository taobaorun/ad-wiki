from __future__ import annotations

import copy
import json
import re
from pathlib import PurePosixPath
from typing import Any


SCHEMA_VERSION = "1"
EVIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
NODE_KINDS = {
    "annotation",
    "config-key",
    "constructor",
    "field",
    "file",
    "method",
    "module",
    "package",
    "property",
    "type",
    "unresolved",
}
RELATIONS = {
    "annotates",
    "calls",
    "configured-by",
    "contains",
    "extends",
    "implements",
    "imports",
    "references",
    "tests",
    "uses",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _relative_source_file(value: Any) -> bool:
    if not isinstance(value, str) or not value or re.match(r"^[A-Za-z]:[\\/]", value):
        return False
    path = PurePosixPath(value.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def _location_errors(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} source_location must be an object"]
    start = value.get("start_line")
    end = value.get("end_line")
    if type(start) is not int or type(end) is not int or start < 1 or end < start:
        return [f"{label} source_location must have 1 <= start_line <= end_line"]
    return []


def _node_errors(value: Any, index: int) -> list[str]:
    label = f"node {index}"
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    for key in ("id", "label", "kind", "language", "source_file", "source_location"):
        if key not in value:
            errors.append(f"{label} missing {key}")
    if value.get("kind") not in NODE_KINDS:
        errors.append(f"{label} has invalid kind")
    for key in ("id", "label", "language", "source_file"):
        if key in value and (not isinstance(value[key], str) or not value[key]):
            errors.append(f"{label} {key} must be non-empty text")
    if "source_file" in value and not _relative_source_file(value["source_file"]):
        errors.append(f"{label} source_file must be repository-relative")
    if "summary" in value and (
        not isinstance(value["summary"], str) or len(value["summary"]) > 300
    ):
        errors.append(f"{label} summary exceeds deterministic limit")
    if "source_location" in value:
        errors.extend(_location_errors(value["source_location"], label))
    return errors


def _edge_errors(value: Any, index: int, node_ids: set[str]) -> list[str]:
    label = f"edge {index}"
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    for key in ("source", "target", "relation", "evidence", "source_file", "source_location"):
        if key not in value:
            errors.append(f"{label} missing {key}")
    if value.get("source") not in node_ids:
        errors.append(f"{label} has dangling source")
    if value.get("target") not in node_ids:
        errors.append(f"{label} has dangling target")
    if value.get("relation") not in RELATIONS:
        errors.append(f"{label} has invalid relation")
    if value.get("evidence") not in EVIDENCE:
        errors.append(f"{label} has invalid evidence")
    if not isinstance(value.get("source_file"), str) or not value.get("source_file"):
        errors.append(f"{label} source_file must be non-empty text")
    elif not _relative_source_file(value["source_file"]):
        errors.append(f"{label} source_file must be repository-relative")
    if "source_location" in value:
        errors.extend(_location_errors(value["source_location"], label))
    return errors


def _nodes_and_edges_errors(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = value.get("nodes")
    edges = value.get("edges")
    if not isinstance(nodes, list):
        return ["nodes must be a list"]
    if not isinstance(edges, list):
        return ["edges must be a list"]
    node_ids: set[str] = set()
    for index, item in enumerate(nodes):
        errors.extend(_node_errors(item, index))
        node_id = item.get("id") if isinstance(item, dict) else None
        if isinstance(node_id, str):
            if node_id in node_ids:
                errors.append(f"duplicate node id: {node_id}")
            node_ids.add(node_id)
    for index, item in enumerate(edges):
        errors.extend(_edge_errors(item, index, node_ids))
    return errors


def validate_fragment(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["Fragment must be an object"]
    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("Fragment schema_version is unsupported")
    extractor = value.get("extractor")
    if not isinstance(extractor, dict) or not all(
        isinstance(extractor.get(key), str) and extractor.get(key)
        for key in ("name", "version", "grammar")
    ):
        errors.append("Fragment extractor identity is invalid")
    source = value.get("source")
    if not isinstance(source, dict):
        errors.append("Fragment source is invalid")
    else:
        if not isinstance(source.get("path"), str) or not source.get("path"):
            errors.append("Fragment source path is invalid")
        if not isinstance(source.get("sha256"), str) or not SHA256.fullmatch(source["sha256"]):
            errors.append("Fragment source sha256 is invalid")
        if type(source.get("bytes")) is not int or source["bytes"] < 0:
            errors.append("Fragment source bytes is invalid")
    if not isinstance(value.get("unresolved"), list):
        errors.append("Fragment unresolved must be a list")
    else:
        node_ids = {
            item.get("id")
            for item in value.get("nodes", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for index, item in enumerate(value["unresolved"]):
            if not isinstance(item, dict):
                errors.append(f"unresolved {index} must be an object")
                continue
            if item.get("node_id") not in node_ids or item.get("source") not in node_ids:
                errors.append(f"unresolved {index} references a missing node")
            if item.get("relation") not in RELATIONS or not isinstance(item.get("token"), str):
                errors.append(f"unresolved {index} has invalid relation or token")
    errors.extend(_nodes_and_edges_errors(value))
    return errors


def validate_graph(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["Graph must be an object"]
    errors: list[str] = []
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append("Graph schema_version is unsupported")
    revision = value.get("revision")
    if not isinstance(revision, str) or not GIT_SHA.fullmatch(revision):
        errors.append("Graph revision is invalid")
    if not isinstance(value.get("vocab"), list) or not all(
        isinstance(item, str) for item in value.get("vocab", [])
    ):
        errors.append("Graph vocab must be a string list")
    errors.extend(_nodes_and_edges_errors(value))
    return errors


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    stable = copy.deepcopy(value)
    if isinstance(stable.get("nodes"), list):
        stable["nodes"] = sorted(stable["nodes"], key=lambda item: item.get("id", ""))
    if isinstance(stable.get("edges"), list):
        stable["edges"] = sorted(
            stable["edges"],
            key=lambda item: (
                item.get("source", ""),
                item.get("relation", ""),
                item.get("target", ""),
                item.get("source_file", ""),
                item.get("source_location", {}).get("start_line", 0),
            ),
        )
    if isinstance(stable.get("vocab"), list):
        stable["vocab"] = sorted(set(stable["vocab"]))
    return (json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
