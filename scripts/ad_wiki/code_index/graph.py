from __future__ import annotations

import re

from ..core import ADWikiError
from .model import validate_fragment, validate_graph


def _tokens(value: str) -> set[str]:
    parts: set[str] = set()
    for chunk in re.findall(r"[^\W\d_]+", value, re.UNICODE):
        split = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[a-z]+", chunk) or [chunk]
        for item in split:
            token = item.lower()
            if 3 <= len(token) <= 40:
                parts.add(token)
    return parts


def _summary(node: dict, nodes: list[dict], edges: list[dict]) -> str:
    if node.get("kind") not in {"file", "type"}:
        return ""
    if node.get("doc_summary"):
        return str(node["doc_summary"])[:300]
    node_id = node["id"]
    children = [
        item["target"]
        for item in edges
        if item["source"] == node_id and item["relation"] == "contains"
    ]
    by_id = {item["id"]: item for item in nodes}
    labels = [by_id[item]["label"] for item in children if item in by_id][:8]
    relations = sorted(
        {
            item["relation"]
            for item in edges
            if item["source"] == node_id or item["target"] == node_id
        }
    )
    text = f"{node['label']} defines {', '.join(labels) or 'structural declarations'}"
    if relations:
        text += f"; relations: {', '.join(relations)}"
    return text[:300]


def _candidate_types(token: str, package: str, imports: list[str], type_by_qualified: dict[str, str]) -> list[str]:
    simple = token.split(".")[-1]
    candidates: list[str] = []
    if token in type_by_qualified:
        candidates.append(type_by_qualified[token])
    local = f"{package}.{token}".strip(".")
    if local in type_by_qualified:
        candidates.append(type_by_qualified[local])
    for imported in imports:
        if imported.endswith(f".{simple}") and imported in type_by_qualified:
            candidates.append(type_by_qualified[imported])
    candidates.extend(
        node_id
        for qualified, node_id in type_by_qualified.items()
        if qualified.split(".")[-1] == simple
    )
    return sorted(set(candidates))


def build_graph(fragments: list[dict], *, revision: str) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    unresolved: list[dict] = []
    for fragment in sorted(fragments, key=lambda item: item.get("source", {}).get("path", "")):
        errors = validate_fragment(fragment)
        if errors:
            raise ADWikiError("invalid structural Fragment: " + "; ".join(errors))
        for item in fragment["nodes"]:
            existing = nodes.get(item["id"])
            if existing is not None and existing != item:
                raise ADWikiError(f"conflicting duplicate structural node: {item['id']}")
            nodes[item["id"]] = dict(item)
        edges.extend(dict(item) for item in fragment["edges"])
        unresolved.extend(dict(item) for item in fragment.get("unresolved", []))

    type_by_qualified = {
        str(item["qualified_name"]): item["id"]
        for item in nodes.values()
        if item.get("kind") == "type" and item.get("qualified_name")
    }
    methods_by_name_arity: dict[tuple[str, int], list[str]] = {}
    methods_by_owner_name_arity: dict[tuple[str, str, int], list[str]] = {}
    for item in nodes.values():
        if item.get("kind") not in {"method", "constructor"}:
            continue
        key = (str(item.get("name", "")), int(item.get("arity", 0)))
        methods_by_name_arity.setdefault(key, []).append(item["id"])
        methods_by_owner_name_arity.setdefault(
            (str(item.get("owner", "")), key[0], key[1]), []
        ).append(item["id"])

    facts = {item["node_id"]: item for item in unresolved}
    resolved_edges: list[dict] = []
    resolved_unresolved: set[str] = set()
    for item in edges:
        fact = facts.get(item["target"])
        if fact is None:
            resolved_edges.append(item)
            continue
        relation = fact["relation"]
        candidates: list[str] = []
        if relation in {"imports", "extends", "implements", "annotates"}:
            candidates = _candidate_types(
                str(fact["token"]),
                str(fact.get("package", "")),
                list(fact.get("imports", [])),
                type_by_qualified,
            )
        elif relation == "calls":
            token = str(fact["token"])
            name = token.split(".")[-1]
            arity = int(fact.get("arity") or 0)
            qualifier = fact.get("qualifier")
            if qualifier:
                type_candidates = _candidate_types(
                    str(qualifier),
                    str(fact.get("package", "")),
                    list(fact.get("imports", [])),
                    type_by_qualified,
                )
                owners = [str(nodes[node_id].get("qualified_name", "")) for node_id in type_candidates]
                for owner in owners:
                    candidates.extend(methods_by_owner_name_arity.get((owner, name, arity), []))
            else:
                candidates.extend(
                    methods_by_owner_name_arity.get(
                        (str(fact.get("owner", "")), name, arity), []
                    )
                )
            if not candidates:
                candidates.extend(methods_by_name_arity.get((name, arity), []))
        candidates = sorted(set(candidates))
        if len(candidates) == 1:
            resolved = dict(item)
            resolved["target"] = candidates[0]
            resolved["evidence"] = "INFERRED" if item["evidence"] == "AMBIGUOUS" else item["evidence"]
            resolved_edges.append(resolved)
            resolved_unresolved.add(item["target"])
        else:
            nodes[item["target"]]["candidates"] = candidates[:20]
            item["evidence"] = "AMBIGUOUS"
            resolved_edges.append(item)

    referenced = {item["source"] for item in resolved_edges} | {item["target"] for item in resolved_edges}
    for node_id in resolved_unresolved:
        if node_id not in referenced:
            nodes.pop(node_id, None)

    edge_keys: set[tuple] = set()
    deduped_edges: list[dict] = []
    for item in resolved_edges:
        key = (
            item["source"],
            item["target"],
            item["relation"],
            item["evidence"],
            item["source_file"],
            item["source_location"]["start_line"],
            item["source_location"]["end_line"],
        )
        if key not in edge_keys:
            edge_keys.add(key)
            deduped_edges.append(item)

    node_values = sorted(nodes.values(), key=lambda item: item["id"])
    edge_values = sorted(
        deduped_edges,
        key=lambda item: (
            item["source"],
            item["relation"],
            item["target"],
            item["source_file"],
            item["source_location"]["start_line"],
        ),
    )
    for item in node_values:
        summary = _summary(item, node_values, edge_values)
        if summary:
            item["summary"] = summary
            item["summary_generated_by"] = "deterministic"
            item["summary_version"] = 1
    vocab: set[str] = set()
    for item in node_values:
        vocab.update(_tokens(str(item.get("label", ""))))
        vocab.update(_tokens(str(item.get("qualified_name", ""))))
    graph = {
        "schema_version": "1",
        "revision": revision,
        "nodes": node_values,
        "edges": edge_values,
        "vocab": sorted(vocab),
    }
    errors = validate_graph(graph)
    if errors:
        raise ADWikiError("invalid structural graph: " + "; ".join(errors))
    return graph
