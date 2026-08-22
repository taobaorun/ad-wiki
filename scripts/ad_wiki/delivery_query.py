from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


class DeliveryQueryError(RuntimeError):
    pass


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _has_symlink(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _read_json_object(root: Path, relative: str, label: str) -> dict[str, Any]:
    lexical_path = root / relative
    path = lexical_path.resolve()
    if (
        _has_symlink(lexical_path, root)
        or not _inside(path, root)
        or not path.is_file()
    ):
        raise DeliveryQueryError(f"{label} must be a regular packaged file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DeliveryQueryError(f"{label} must contain an object")
    return value


def _configured_directory(root: Path, value: Any, label: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or Path(value).is_absolute()
        or ".." in Path(value).parts
    ):
        raise DeliveryQueryError(f"{label} must remain inside the packaged repository")
    lexical_path = root / value
    path = lexical_path.resolve()
    if _has_symlink(lexical_path, root) or not _inside(path, root) or not path.is_dir():
        raise DeliveryQueryError(f"{label} must remain inside the packaged repository")
    return path


def _frontmatter(text: str) -> list[str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise DeliveryQueryError("selected Concept lacks frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index]
    raise DeliveryQueryError("selected Concept has unclosed frontmatter")


def _sources(lines: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_sources = False
    for line in lines:
        if line.startswith("sources:"):
            in_sources = True
            continue
        if in_sources and line and not line[0].isspace():
            break
        if not in_sources:
            continue
        item = re.match(r"^\s+-\s+([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*$", line)
        nested = re.match(r"^\s+([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*$", line)
        if item:
            if current is not None:
                entries.append(current)
            current = {item.group(1): item.group(2).strip("\"'")}
        elif nested and current is not None:
            current[nested.group(1)] = nested.group(2).strip("\"'")
    if current is not None:
        entries.append(current)
    return entries


def _tokens(value: str) -> list[str]:
    values = re.findall(r"[a-z0-9_.-]{2,}|[\u3400-\u9fff]{2,}", value.casefold())
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
        if "\u3400" <= value[0] <= "\u9fff":
            result.extend(
                value[index : index + 2] for index in range(max(0, len(value) - 1))
            )
    return list(dict.fromkeys(result))


def _excerpt(text: str, terms: list[str], budget: int) -> tuple[str, int, int] | None:
    lines = text.splitlines()
    ranked: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        normalized = line.casefold()
        score = sum(
            (len(term) + normalized.count(term)) for term in terms if term in normalized
        )
        if score:
            ranked.append((score, index))
    if not ranked:
        return None
    _, index = max(ranked, key=lambda item: (item[0], -item[1]))
    previous_headings = [
        value for value in range(index, -1, -1) if lines[value].lstrip().startswith("#")
    ]
    next_headings = [
        value
        for value in range(index + 1, len(lines))
        if lines[value].lstrip().startswith("#")
    ]
    section_start = previous_headings[0] if previous_headings else max(0, index - 3)
    section_end = next_headings[0] if next_headings else len(lines)
    if section_end - section_start > 80:
        start = max(0, index - 3)
        end = min(len(lines), index + 9)
    else:
        start = section_start
        end = section_end
    content = "\n".join(lines[start:end]).strip()[:budget]
    return content, start + 1, end


def query_registered_raw(
    repo: str | Path,
    *,
    query: str,
    concept_ids: Iterable[str],
    max_sources: int = 2,
    max_chars: int = 6_000,
) -> dict[str, Any]:
    if not query.strip():
        raise DeliveryQueryError("query must be non-empty")
    if not 1 <= max_sources <= 5:
        raise DeliveryQueryError("max-sources must be between 1 and 5")
    if not 1 <= max_chars <= 100_000:
        raise DeliveryQueryError("max-chars must be between 1 and 100000")
    selected = list(dict.fromkeys(concept_ids))
    if not selected or len(selected) > 8:
        raise DeliveryQueryError("select between 1 and 8 Concepts")
    terms = _tokens(query)
    if not terms:
        raise DeliveryQueryError("query has no searchable terms")

    unresolved_root = Path(repo).expanduser()
    if unresolved_root.is_symlink():
        raise DeliveryQueryError("repository must be a regular directory")
    root = unresolved_root.resolve()
    if not root.is_dir():
        raise DeliveryQueryError("repository must be a regular directory")
    config = _read_json_object(root, "ad-wiki.yaml", "configuration")
    bundle = _configured_directory(
        root, config.get("bundle_root", "wiki"), "bundle_root"
    )
    raw_root = _configured_directory(root, config.get("raw_root", "raw"), "raw_root")
    registry = _read_json_object(
        root, ".ad-wiki/source-registry.json", "source registry"
    )
    records = registry.get("sources", [])
    if (
        registry.get("version") != 1
        or not isinstance(records, list)
        or not all(isinstance(record, dict) for record in records)
    ):
        raise DeliveryQueryError("source registry format is unsupported")
    linked: list[dict[str, Any]] = []
    for concept_id in selected:
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,255}", concept_id)
            or ".." in Path(concept_id).parts
        ):
            raise DeliveryQueryError(f"invalid Concept ID: {concept_id}")
        lexical_path = bundle / f"{concept_id}.md"
        path = lexical_path.resolve()
        if (
            _has_symlink(lexical_path, bundle)
            or not _inside(path, bundle)
            or not path.is_file()
        ):
            raise DeliveryQueryError(
                f"Concept is not a readable packaged file: {concept_id}"
            )
        for entry in _sources(_frontmatter(path.read_text(encoding="utf-8"))):
            resource = entry.get("resource", "")
            locator_matches = [
                record
                for record in records
                if resource == record.get("canonical_locator")
            ]
            matches: list[dict[str, Any]]
            if locator_matches:
                matches = [
                    max(locator_matches, key=lambda record: int(record["version"]))
                ]
            elif resource and "://" not in resource and not resource.startswith("git@"):
                resource_path = (path.parent / resource).resolve()
                matches = [
                    record
                    for record in records
                    if resource_path == (root / str(record.get("path", ""))).resolve()
                ]
            else:
                matches = [
                    record
                    for record in records
                    if entry.get("id") == record.get("source_id")
                ]
            if len(matches) > 1:
                raise DeliveryQueryError(f"Concept source is ambiguous: {concept_id}")
            for record in matches:
                if record not in linked:
                    linked.append(record)
    if not linked:
        raise DeliveryQueryError("selected Concepts have no registered Raw sources")

    sources: list[dict[str, Any]] = []
    remaining = max_chars
    for record in linked[:max_sources]:
        record_path = record.get("path")
        if (
            not isinstance(record_path, str)
            or not record_path
            or Path(record_path).is_absolute()
            or ".." in Path(record_path).parts
        ):
            raise DeliveryQueryError(
                "registered Raw source path must remain inside the packaged repository"
            )
        lexical_path = root / record_path
        path = lexical_path.resolve()
        if (
            _has_symlink(lexical_path, root)
            or not _inside(path, raw_root)
            or not path.is_file()
        ):
            raise DeliveryQueryError(
                f"registered Raw source is unavailable: {record['path']}"
            )
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record.get("sha256"):
            raise DeliveryQueryError(f"registered Raw source changed: {record['path']}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DeliveryQueryError(
                f"registered Raw source is not UTF-8 text: {record['path']}"
            ) from exc
        excerpt = _excerpt(text, terms, remaining)
        if excerpt is None:
            continue
        content, start_line, end_line = excerpt
        remaining -= len(content)
        sources.append(
            {
                "canonical_locator": record["canonical_locator"],
                "excerpts": [
                    {"content": content, "end_line": end_line, "start_line": start_line}
                ],
                "integrity": "verified",
                "path": record["path"],
                "registry_source_id": record["source_id"],
                "version": record["version"],
            }
        )
        if remaining == 0:
            break
    return {
        "concepts": selected,
        "mode": "raw-fallback",
        "query": query,
        "retrieval": {
            "included_chars": max_chars - remaining,
            "included_source_count": len(sources),
            "linked_source_count": len(linked),
            "max_chars": max_chars,
            "max_sources": max_sources,
        },
        "schema_version": "1",
        "sources": sources,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read bounded registered Raw from a delivered AD Wiki Skill."
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--concept", action="append", required=True, dest="concept_ids")
    parser.add_argument("--max-sources", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=6_000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = query_registered_raw(
            args.repo,
            query=args.query,
            concept_ids=args.concept_ids,
            max_sources=args.max_sources,
            max_chars=args.max_chars,
        )
    except (
        DeliveryQueryError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        payload = {"error": str(exc), "status": "error"}
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
