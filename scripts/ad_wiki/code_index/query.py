from __future__ import annotations

import json
from collections import deque
from typing import Any

from ..core import ADWikiError
from .model import validate_graph


DEFAULT_RELATIONS = {"calls", "imports", "extends", "implements", "references", "uses"}


def _neighbors(edges: list[dict], node_id: str, *, reverse_only: bool = False, relations: set[str] | None = None) -> list[tuple[str, dict]]:
    result: list[tuple[str, dict]] = []
    for edge in edges:
        if relations is not None and edge["relation"] not in relations:
            continue
        if edge["target"] == node_id:
            result.append((edge["source"], edge))
        if not reverse_only and edge["source"] == node_id:
            result.append((edge["target"], edge))
    return sorted(result, key=lambda item: (item[0], item[1]["relation"]))


def _search_nodes(graph: dict, tokens: list[str]) -> tuple[list[str], list[str], list[dict]]:
    vocab = set(graph.get("vocab", []))
    valid = [token.lower() for token in tokens if token.lower() in vocab]
    diagnostics = [f"token not present in graph vocabulary: {token}" for token in tokens if token.lower() not in vocab]
    if not valid:
        return [], diagnostics, []
    scored: list[tuple[int, str]] = []
    token_matches: dict[str, list[str]] = {token: [] for token in valid}
    for node in graph["nodes"]:
        haystack = " ".join(
            str(node.get(key, "")).lower()
            for key in ("id", "label", "source_file", "qualified_name")
        )
        score = sum(1 for token in valid if token in haystack)
        if score:
            scored.append((score, node["id"]))
            for token in valid:
                if token in str(node.get("label", "")).lower():
                    token_matches[token].append(node["id"])
    scored.sort(key=lambda item: (-item[0], item[1]))
    ambiguities = [
        {"token": token, "candidate_ids": sorted(ids)[:20]}
        for token, ids in token_matches.items()
        if len(ids) > 1
    ]
    return [node_id for _, node_id in scored], diagnostics, ambiguities


def _path(edges: list[dict], source: str, target: str) -> tuple[list[str], list[dict]]:
    queue: deque[str] = deque([source])
    previous: dict[str, tuple[str, dict] | None] = {source: None}
    while queue:
        current = queue.popleft()
        if current == target:
            break
        for neighbor, edge in _neighbors(edges, current):
            if neighbor not in previous:
                previous[neighbor] = (current, edge)
                queue.append(neighbor)
    if target not in previous:
        return [], []
    nodes = [target]
    path_edges: list[dict] = []
    current = target
    while previous[current] is not None:
        parent, edge = previous[current]
        nodes.append(parent)
        path_edges.append(edge)
        current = parent
    nodes.reverse()
    path_edges.reverse()
    return nodes, path_edges


def query_graph(graph: dict, request: dict[str, Any]) -> dict[str, Any]:
    errors = validate_graph(graph)
    if errors:
        raise ADWikiError("cannot query invalid structural graph: " + "; ".join(errors))
    mode = request.get("mode", "search")
    if mode not in {"search", "explain", "path", "bfs", "dfs", "affected"}:
        raise ADWikiError(f"unsupported structural query mode: {mode}")
    max_depth = min(max(int(request.get("max_depth", 3)), 0), 6)
    max_nodes = min(max(int(request.get("max_nodes", 200)), 1), 10_000)
    max_edges = min(max(int(request.get("max_edges", 500)), 0), 20_000)
    max_chars = min(max(int(request.get("max_chars", 20_000)), 100), 1_000_000)
    by_id = {item["id"]: item for item in graph["nodes"]}
    selected_nodes: list[str] = []
    selected_edges: list[dict] = []
    diagnostics: list[str] = []
    ambiguities: list[dict] = []

    if mode == "search":
        selected_nodes, diagnostics, ambiguities = _search_nodes(graph, list(request.get("tokens", [])))
    elif mode == "path":
        source, target = request.get("source_id"), request.get("target_id")
        if source not in by_id or target not in by_id:
            diagnostics.append("path source_id or target_id is not in graph")
        else:
            selected_nodes, selected_edges = _path(graph["edges"], source, target)
            if not selected_nodes:
                diagnostics.append("no path found")
    else:
        source = request.get("source_id")
        if source not in by_id:
            diagnostics.append("source_id is not in graph")
        elif mode == "explain":
            selected_nodes = [source] + [item[0] for item in _neighbors(graph["edges"], source)]
            selected_edges = [item[1] for item in _neighbors(graph["edges"], source)]
        else:
            relations = set(request.get("relations", DEFAULT_RELATIONS))
            reverse = mode == "affected"
            seed_nodes = [source]
            if reverse:
                seed_seen = {source}
                seed_queue: deque[str] = deque([source])
                while seed_queue:
                    parent = seed_queue.popleft()
                    for item in graph["edges"]:
                        if item["source"] != parent or item["relation"] != "contains":
                            continue
                        child = item["target"]
                        if child not in seed_seen:
                            seed_seen.add(child)
                            seed_nodes.append(child)
                            seed_queue.append(child)
            seen = set(seed_nodes)
            selected_nodes = list(dict.fromkeys(seed_nodes))
            if mode == "dfs":
                pending: list[tuple[str, int]] = [(item, 0) for item in reversed(seed_nodes)]
                pop = pending.pop
                push = pending.append
            else:
                queue: deque[tuple[str, int]] = deque((item, 0) for item in seed_nodes)
                pop = queue.popleft
                push = queue.append
                pending = queue  # type: ignore[assignment]
            while pending:
                current, depth = pop()
                if depth >= max_depth:
                    continue
                for neighbor, edge in _neighbors(
                    graph["edges"], current, reverse_only=reverse, relations=relations
                ):
                    selected_edges.append(edge)
                    if neighbor not in seen:
                        seen.add(neighbor)
                        selected_nodes.append(neighbor)
                        push((neighbor, depth + 1))

    original_node_count = len(selected_nodes)
    selected_nodes = list(dict.fromkeys(selected_nodes))[:max_nodes]
    selected_set = set(selected_nodes)
    eligible_edges = [
        item for item in selected_edges if item["source"] in selected_set and item["target"] in selected_set
    ]
    original_edge_count = len(eligible_edges)
    selected_edges = eligible_edges[:max_edges]
    result = {
        "schema_version": "1",
        "mode": mode,
        "revision": graph["revision"],
        "matched_tokens": [token.lower() for token in request.get("tokens", []) if token.lower() in set(graph.get("vocab", []))],
        "start_nodes": [item for item in (request.get("source_id"), request.get("target_id")) if item in selected_set],
        "nodes": [by_id[item] for item in selected_nodes if item in by_id],
        "edges": selected_edges,
        "truncated": original_node_count > len(selected_nodes),
        "ambiguities": ambiguities,
        "diagnostics": diagnostics,
    }
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if len(encoded) > max_chars:
        result["truncated"] = True
        while result["nodes"] and len(json.dumps(result, ensure_ascii=False, sort_keys=True)) > max_chars:
            removed = result["nodes"].pop()
            selected_set.discard(removed["id"])
            result["edges"] = [
                item
                for item in result["edges"]
                if item["source"] in selected_set and item["target"] in selected_set
            ]
    if original_node_count > max_nodes or original_edge_count > max_edges:
        result["truncated"] = True
    return result
