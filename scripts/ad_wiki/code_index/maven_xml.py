from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ..core import ADWikiError
from .ids import stable_symbol_id


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str:
    for child in node:
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _line(text: str, needle: str) -> int:
    index = text.find(needle)
    return text.count("\n", 0, max(index, 0)) + 1


class MavenXmlExtractor:
    name = "maven-xml"
    version = "1"

    def supports(self, path: Path) -> bool:
        return path.name == "pom.xml" or path.suffix.lower() == ".xml"

    def extract(self, path: Path, *, root: Path, content: bytes) -> dict:
        text = content.decode("utf-8")
        if re.search(r"<!DOCTYPE|<!ENTITY", text, re.IGNORECASE):
            raise ADWikiError("XML DOCTYPE and ENTITY declarations are forbidden")
        try:
            document = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ADWikiError(f"invalid XML source: {exc}") from exc
        relative = path.relative_to(root).as_posix()
        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        def add_node(node_id: str, label: str, kind: str, line: int, **extra: Any) -> str:
            nodes.setdefault(
                node_id,
                {
                    "id": node_id,
                    "kind": kind,
                    "label": label,
                    "language": "xml",
                    "source_file": relative,
                    "source_location": {"start_line": line, "end_line": line},
                    **extra,
                },
            )
            return node_id

        def add_edge(source: str, target: str, relation: str, line: int) -> None:
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "evidence": "EXTRACTED",
                    "source_file": relative,
                    "source_location": {"start_line": line, "end_line": line},
                }
            )

        file_id = add_node(stable_symbol_id("xml", "file", relative), path.name, "file", 1)
        parent = next((item for item in document if _local(item.tag) == "parent"), None)
        group = _child_text(document, "groupId") or (_child_text(parent, "groupId") if parent is not None else "")
        artifact = _child_text(document, "artifactId") or path.parent.name
        coordinate = f"{group}:{artifact}".strip(":")
        module_id = add_node(
            stable_symbol_id("xml", "module", relative, coordinate),
            coordinate,
            "module",
            _line(text, f"<artifactId>{artifact}</artifactId>"),
            coordinate=coordinate,
        )
        add_edge(file_id, module_id, "contains", 1)

        properties: dict[str, str] = {}
        for element in document.iter():
            if _local(element.tag) == "properties":
                for child in element:
                    key = _local(child.tag)
                    value = (child.text or "").strip()
                    properties[key] = value
                    prop_id = add_node(
                        stable_symbol_id("xml", "property", relative, key),
                        key,
                        "property",
                        _line(text, f"<{key}>") ,
                        value=value,
                    )
                    add_edge(module_id, prop_id, "contains", nodes[prop_id]["source_location"]["start_line"])

        for element in document.iter():
            kind = _local(element.tag)
            if kind not in {"dependency", "plugin", "module"}:
                continue
            if kind == "module":
                module_name = (element.text or "").strip()
                if not module_name:
                    continue
                target_label = module_name
            else:
                target_group = _child_text(element, "groupId")
                target_artifact = _child_text(element, "artifactId")
                if not target_artifact:
                    continue
                target_label = f"{target_group}:{target_artifact}".strip(":")
            line = _line(text, target_label.split(":")[-1])
            target_id = add_node(
                stable_symbol_id("xml", "module", relative, f"{kind}:{target_label}"),
                target_label,
                "module",
                line,
                module_kind=kind,
            )
            add_edge(module_id, target_id, "uses", line)
            serialized = ET.tostring(element, encoding="unicode")
            for placeholder in re.findall(r"\$\{([^}]+)\}", serialized):
                prop_id = stable_symbol_id("xml", "property", relative, placeholder)
                if prop_id in nodes:
                    add_edge(target_id, prop_id, "references", line)

        return {
            "schema_version": "1",
            "extractor": {"grammar": "stdlib-xml/1", "name": self.name, "version": self.version},
            "source": {"bytes": 0, "path": relative, "sha256": "0" * 64},
            "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
            "edges": sorted(edges, key=lambda item: (item["source"], item["relation"], item["target"])),
            "unresolved": [],
        }


MAVEN_XML_EXTRACTOR = MavenXmlExtractor()
