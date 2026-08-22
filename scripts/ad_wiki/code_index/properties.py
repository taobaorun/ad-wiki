from __future__ import annotations

import re
from pathlib import Path

from .ids import stable_symbol_id


SENSITIVE_KEY = re.compile(r"(?i)(?:password|secret|token|credential|api[_-]?key|private[_-]?key)")
PLACEHOLDER = re.compile(r"\$\{([^}:]+)(?::[^}]*)?\}")


class PropertiesExtractor:
    name = "properties"
    version = "1"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".properties"

    def extract(self, path: Path, *, root: Path, content: bytes) -> dict:
        relative = path.relative_to(root).as_posix()
        text = content.decode("utf-8")
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        file_id = stable_symbol_id("properties", "file", relative)
        nodes[file_id] = {
            "id": file_id,
            "kind": "file",
            "label": path.name,
            "language": "properties",
            "source_file": relative,
            "source_location": {"start_line": 1, "end_line": max(1, len(text.splitlines()))},
        }
        values: list[tuple[str, str, int]] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "!")):
                continue
            match = re.match(r"([^:=\s]+)\s*[:=]\s*(.*)", line)
            if not match:
                continue
            key, value = match.group(1).strip(), match.group(2).strip()
            sensitive = bool(SENSITIVE_KEY.search(key))
            node_id = stable_symbol_id("properties", "config-key", relative, key)
            nodes[node_id] = {
                "id": node_id,
                "kind": "config-key",
                "label": key,
                "language": "properties",
                "sensitive": sensitive,
                "source_file": relative,
                "source_location": {"start_line": line_number, "end_line": line_number},
                "value": "<redacted>" if sensitive else value,
            }
            edges.append(
                {
                    "source": file_id,
                    "target": node_id,
                    "relation": "contains",
                    "evidence": "EXTRACTED",
                    "source_file": relative,
                    "source_location": {"start_line": line_number, "end_line": line_number},
                }
            )
            values.append((node_id, value, line_number))
        for source_id, value, line_number in values:
            for target_key in PLACEHOLDER.findall(value):
                target_id = stable_symbol_id("properties", "config-key", relative, target_key)
                if target_id not in nodes:
                    target_id = stable_symbol_id(
                        "properties",
                        "unresolved",
                        relative,
                        f"{target_key}@L{line_number}",
                    )
                    nodes[target_id] = {
                        "id": target_id,
                        "kind": "unresolved",
                        "label": target_key,
                        "language": "properties",
                        "source_file": relative,
                        "source_location": {"start_line": line_number, "end_line": line_number},
                    }
                edges.append(
                    {
                        "source": source_id,
                        "target": target_id,
                        "relation": "references",
                        "evidence": "EXTRACTED" if nodes[target_id]["kind"] != "unresolved" else "AMBIGUOUS",
                        "source_file": relative,
                        "source_location": {"start_line": line_number, "end_line": line_number},
                    }
                )
        return {
            "schema_version": "1",
            "extractor": {"grammar": "properties/1", "name": self.name, "version": self.version},
            "source": {"bytes": 0, "path": relative, "sha256": "0" * 64},
            "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
            "edges": sorted(edges, key=lambda item: (item["source"], item["relation"], item["target"])),
            "unresolved": [],
        }


PROPERTIES_EXTRACTOR = PropertiesExtractor()
