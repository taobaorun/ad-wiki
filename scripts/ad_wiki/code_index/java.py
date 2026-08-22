from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from .ids import stable_symbol_id


TYPE_NODES = {
    "annotation_type_declaration",
    "class_declaration",
    "enum_declaration",
    "interface_declaration",
    "record_declaration",
}


def _location(node: Any) -> dict[str, int]:
    return {"start_line": node.start_point[0] + 1, "end_line": node.end_point[0] + 1}


def _text(content: bytes, node: Any | None) -> str:
    if node is None:
        return ""
    return content[node.start_byte : node.end_byte].decode("utf-8")


def _walk(node: Any) -> Iterator[Any]:
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _annotation_names(node: Any, content: bytes) -> list[tuple[str, Any]]:
    modifiers = next((child for child in node.named_children if child.type == "modifiers"), None)
    if modifiers is None:
        return []
    result: list[tuple[str, Any]] = []
    for child in modifiers.named_children:
        if child.type in {"annotation", "marker_annotation"}:
            name = child.child_by_field_name("name")
            value = _text(content, name) or _text(content, child).lstrip("@").split("(", 1)[0]
            result.append((value, child))
    return result


def _erase_type(value: str) -> str:
    result: list[str] = []
    depth = 0
    for char in value:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif depth == 0 and not char.isspace():
            result.append(char)
    return "".join(result).replace("...", "[]")


def _comment_summary(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"(?m)^\s*[/!*]+\s?", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return sentence[:300]


def _preceding_javadoc(content: bytes, start_byte: int) -> str:
    prefix = content[:start_byte].decode("utf-8", errors="ignore")
    match = re.search(r"/\*\*(.*?)\*/\s*(?:@[\w.]+(?:\([^)]*\))?\s*)*$", prefix, re.DOTALL)
    return _comment_summary(match.group(1)) if match else ""


def _leading_javadoc(content: bytes) -> str:
    match = re.match(r"\s*/\*\*(.*?)\*/", content.decode("utf-8", errors="ignore"), re.DOTALL)
    return _comment_summary(match.group(1)) if match else ""


def _parameter_types(node: Any, content: bytes) -> list[str]:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return []
    result: list[str] = []
    for child in parameters.named_children:
        if child.type not in {"formal_parameter", "spread_parameter", "receiver_parameter"}:
            continue
        type_node = child.child_by_field_name("type")
        if type_node is not None:
            result.append(_erase_type(_text(content, type_node)))
    return result


class JavaExtractor:
    name = "java"
    version = "1"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".java"

    def extract(self, path: Path, *, root: Path, content: bytes) -> dict:
        # Official API: https://github.com/tree-sitter/py-tree-sitter/blob/v0.25.2/README.md
        import tree_sitter_java
        from tree_sitter import Language, Parser

        language = Language(tree_sitter_java.language())
        tree = Parser(language).parse(content)
        relative = path.relative_to(root).as_posix()
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        unresolved: list[dict] = []

        def add_node(node_id: str, label: str, kind: str, syntax: Any, **extra: Any) -> str:
            value = {
                "id": node_id,
                "kind": kind,
                "label": label,
                "language": "java",
                "source_file": relative,
                "source_location": _location(syntax),
                **extra,
            }
            nodes.setdefault(node_id, value)
            return node_id

        def add_edge(source: str, target: str, relation: str, evidence: str, syntax: Any) -> None:
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "evidence": evidence,
                    "source_file": relative,
                    "source_location": _location(syntax),
                }
            )

        def unresolved_target(
            source: str,
            token: str,
            relation: str,
            syntax: Any,
            *,
            owner: str | None = None,
            arity: int | None = None,
            qualifier: str | None = None,
            package: str = "",
            imports: list[str] | None = None,
            evidence: str = "AMBIGUOUS",
        ) -> None:
            identity = f"{relation}:{token}/{arity if arity is not None else '-'}@L{syntax.start_point[0] + 1}"
            node_id = stable_symbol_id("java", "unresolved", relative, identity)
            add_node(node_id, token, "unresolved", syntax, candidates=[])
            add_edge(source, node_id, relation, evidence, syntax)
            unresolved.append(
                {
                    "arity": arity,
                    "imports": imports or [],
                    "node_id": node_id,
                    "owner": owner,
                    "package": package,
                    "qualifier": qualifier,
                    "relation": relation,
                    "source": source,
                    "token": token,
                }
            )

        root_node = tree.root_node
        file_id = add_node(
            stable_symbol_id("java", "file", relative),
            path.name,
            "file",
            root_node,
            is_test="test" in {part.lower() for part in Path(relative).parts},
            doc_summary=_leading_javadoc(content),
        )
        package = ""
        imports: list[str] = []
        for child in root_node.named_children:
            if child.type == "package_declaration":
                match = re.search(r"package\s+([\w.]+)", _text(content, child))
                package = match.group(1) if match else ""
                if package:
                    package_id = add_node(
                        stable_symbol_id("java", "package", relative, package),
                        package,
                        "package",
                        child,
                        qualified_name=package,
                    )
                    add_edge(file_id, package_id, "contains", "EXTRACTED", child)
            elif child.type == "import_declaration":
                match = re.search(r"import\s+(?:static\s+)?([\w.*]+)", _text(content, child))
                if match:
                    imports.append(match.group(1))
                    unresolved_target(
                        file_id,
                        match.group(1),
                        "imports",
                        child,
                        package=package,
                        imports=imports,
                        evidence="EXTRACTED",
                    )

        def annotations(source_id: str, syntax: Any, owner: str | None) -> None:
            for name, annotation_node in _annotation_names(syntax, content):
                unresolved_target(
                    source_id,
                    name,
                    "annotates",
                    annotation_node,
                    owner=owner,
                    package=package,
                    imports=imports,
                    evidence="EXTRACTED",
                )

        def type_reference(source_id: str, token: str, relation: str, syntax: Any, owner: str) -> None:
            if token:
                unresolved_target(
                    source_id,
                    _erase_type(token),
                    relation,
                    syntax,
                    owner=owner,
                    package=package,
                    imports=imports,
                    evidence="EXTRACTED",
                )

        def walk_type(
            syntax: Any,
            parent_owner: str | None = None,
            parent_type_id: str | None = None,
        ) -> None:
            name_node = syntax.child_by_field_name("name")
            name = _text(content, name_node)
            if not name:
                return
            owner = f"{parent_owner}.{name}" if parent_owner else f"{package}.{name}".strip(".")
            type_id = add_node(
                stable_symbol_id("java", "type", relative, owner),
                owner,
                "type",
                syntax,
                qualified_name=owner,
                type_kind=syntax.type.replace("_declaration", ""),
                is_test="test" in {part.lower() for part in Path(relative).parts},
                doc_summary=_preceding_javadoc(content, syntax.start_byte),
            )
            add_edge(parent_type_id or file_id, type_id, "contains", "EXTRACTED", syntax)
            annotations(type_id, syntax, owner)

            superclass = syntax.child_by_field_name("superclass")
            if superclass is not None:
                type_reference(type_id, re.sub(r"^extends\s+", "", _text(content, superclass)), "extends", superclass, owner)
            interfaces = syntax.child_by_field_name("interfaces")
            if interfaces is not None:
                text = re.sub(r"^(?:implements|extends)\s+", "", _text(content, interfaces))
                for token in text.split(","):
                    relation = "extends" if syntax.type == "interface_declaration" else "implements"
                    type_reference(type_id, token.strip(), relation, interfaces, owner)

            body = syntax.child_by_field_name("body")
            if body is None:
                return
            for member in body.named_children:
                if member.type in TYPE_NODES:
                    walk_type(member, owner, type_id)
                    continue
                if member.type == "field_declaration":
                    for declarator in [item for item in _walk(member) if item.type == "variable_declarator"]:
                        field_name = _text(content, declarator.child_by_field_name("name"))
                        if field_name:
                            field_id = add_node(
                                stable_symbol_id("java", "field", relative, f"{owner}.{field_name}"),
                                f"{owner}.{field_name}",
                                "field",
                                declarator,
                                owner=owner,
                            )
                            add_edge(type_id, field_id, "contains", "EXTRACTED", declarator)
                    continue
                if member.type not in {"constructor_declaration", "method_declaration"}:
                    continue
                method_name = _text(content, member.child_by_field_name("name"))
                parameters = _parameter_types(member, content)
                symbol = f"{owner}.{method_name}({','.join(parameters)})"
                kind = "constructor" if member.type == "constructor_declaration" else "method"
                method_id = add_node(
                    stable_symbol_id("java", kind, relative, symbol),
                    symbol,
                    kind,
                    member,
                    arity=len(parameters),
                    name=method_name,
                    owner=owner,
                    qualified_name=symbol,
                    is_test=(
                        "test" in {part.lower() for part in Path(relative).parts}
                        or any(name.endswith("Test") for name, _ in _annotation_names(member, content))
                    ),
                )
                add_edge(type_id, method_id, "contains", "EXTRACTED", member)
                annotations(method_id, member, owner)
                body_node = member.child_by_field_name("body")
                if body_node is None:
                    continue
                for invocation in [item for item in _walk(body_node) if item.type == "method_invocation"]:
                    call_name = _text(content, invocation.child_by_field_name("name"))
                    object_node = invocation.child_by_field_name("object")
                    qualifier = _text(content, object_node) or None
                    arguments = invocation.child_by_field_name("arguments")
                    arity = len(arguments.named_children) if arguments is not None else 0
                    token = f"{qualifier}.{call_name}" if qualifier else call_name
                    unresolved_target(
                        method_id,
                        token,
                        "calls",
                        invocation,
                        owner=owner,
                        arity=arity,
                        qualifier=qualifier,
                        package=package,
                        imports=imports,
                    )

        for child in root_node.named_children:
            if child.type in TYPE_NODES:
                walk_type(child)

        return {
            "schema_version": "1",
            "extractor": {
                "grammar": "tree-sitter-java/0.23.5",
                "name": self.name,
                "version": self.version,
            },
            "source": {"bytes": 0, "path": relative, "sha256": "0" * 64},
            "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
            "edges": sorted(
                edges,
                key=lambda item: (
                    item["source"],
                    item["relation"],
                    item["target"],
                    item["source_location"]["start_line"],
                ),
            ),
            "unresolved": sorted(unresolved, key=lambda item: item["node_id"]),
        }


JAVA_EXTRACTOR = JavaExtractor()
