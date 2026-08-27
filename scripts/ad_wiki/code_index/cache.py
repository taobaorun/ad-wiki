from __future__ import annotations

import hashlib
import json
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..core import ADWikiError
from ..code_sources import repository_key
from .extractors import extract_file, provider_for
from .graph import build_graph
from .model import SCHEMA_VERSION, canonical_json_bytes, validate_fragment, validate_graph
from .security import DENIED_PARTS, read_text_source


SUMMARY_VERSION = "1"
MAX_FILES = 100_000
MAX_GRAPH_BYTES = 512 * 1024 * 1024


def cache_root_for(wiki_root: str | Path, code_source: dict[str, Any]) -> Path:
    return Path(wiki_root).expanduser().resolve() / ".ad-wiki/cache/code-index" / repository_key(code_source)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


@contextmanager
def _cache_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ADWikiError("another structural index builder holds the cache lock") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ADWikiError(f"invalid code index artifact {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ADWikiError(f"invalid code index artifact {path.name}: expected object")
    return value


def _supported_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in DENIED_PARTS for part in relative.parts):
            continue
        if provider_for(path) is not None:
            files.append(path)
    files.sort(key=lambda item: item.relative_to(root).as_posix())
    if len(files) > MAX_FILES:
        raise ADWikiError(f"code index file count {len(files)} exceeds limit {MAX_FILES}")
    return files


def _provider_identity(path: Path) -> str:
    provider = provider_for(path)
    if provider is None:
        raise ADWikiError(f"no extractor for {path}")
    grammar = {
        "java": "tree-sitter-java/0.23.5",
        "maven-xml": "stdlib-xml/1",
        "properties": "properties/1",
    }[provider.name]
    return f"{provider.name}/{provider.version}/{grammar}"


def _fragment_key(content: bytes, path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(content)
    for value in (SCHEMA_VERSION, _provider_identity(path), SUMMARY_VERSION):
        digest.update(b"\0")
        digest.update(value.encode())
    return digest.hexdigest()


def _extract_worker(root: str, path: str) -> dict[str, Any]:
    return extract_file(Path(path), root=Path(root))


def load_current_index(cache_root: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(cache_root).expanduser().resolve()
    manifest = _json(root / "manifest.json")
    graph_file = manifest.get("graph_file")
    if not isinstance(graph_file, str) or Path(graph_file).is_absolute() or ".." in Path(graph_file).parts:
        raise ADWikiError("invalid code index manifest graph_file")
    graph_path = (root / graph_file).resolve()
    try:
        graph_path.relative_to(root)
    except ValueError as exc:
        raise ADWikiError("code index graph escapes cache root") from exc
    if not graph_path.is_file() or graph_path.stat().st_size > MAX_GRAPH_BYTES:
        raise ADWikiError("code index graph is missing or exceeds size limit")
    raw = graph_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest.get("graph_sha256"):
        raise ADWikiError("code index graph hash does not match manifest")
    try:
        graph = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ADWikiError("code index graph is invalid JSON") from exc
    errors = validate_graph(graph)
    if errors:
        raise ADWikiError("code index graph validation failed: " + "; ".join(errors))
    return graph, manifest


def load_bindings(cache_root: str | Path) -> dict[str, Any] | None:
    path = Path(cache_root).expanduser().resolve() / "bindings.json"
    if not path.is_file():
        return None
    value = _json(path)
    if value.get("schema_version") != "1" or not isinstance(value.get("concepts"), dict):
        raise ADWikiError("invalid code index bindings schema")
    return value


def publish_bindings(cache_root: str | Path, bindings: dict[str, Any]) -> dict[str, Any]:
    if bindings.get("schema_version") != "1" or not isinstance(bindings.get("concepts"), dict):
        raise ADWikiError("invalid code index bindings schema")
    root = Path(cache_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    content = canonical_json_bytes(bindings)
    _atomic_write(root / "bindings.json", content)
    return {"bindings_sha256": hashlib.sha256(content).hexdigest(), "status": "published"}


def _build_or_update_index_unlocked(
    code_root: str | Path,
    *,
    cache_root: str | Path,
    revision: str,
    workers: int = 1,
    fail_before_manifest: bool = False,
) -> dict[str, Any]:
    if workers < 1:
        raise ADWikiError("code index workers must be positive")
    worker_count = min(workers, 4)
    source_root = Path(code_root).expanduser().resolve()
    target = Path(cache_root).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    ignore = target / ".gitignore"
    if not ignore.exists():
        _atomic_write(ignore, b"*\n")
    fragments_dir = target / "fragments"
    graphs_dir = target / "graphs"
    fragments_dir.mkdir(exist_ok=True)
    graphs_dir.mkdir(exist_ok=True)

    old_manifest: dict[str, Any] = {}
    if (target / "manifest.json").is_file():
        try:
            _, old_manifest = load_current_index(target)
        except ADWikiError:
            old_manifest = {}
    old_files = old_manifest.get("files", {}) if isinstance(old_manifest.get("files"), dict) else {}

    fragments_by_path: dict[str, dict] = {}
    current_files: dict[str, dict[str, str]] = {}
    parsed = 0
    cache_hits = 0
    corrupt = 0
    files = _supported_files(source_root)
    missing: list[tuple[Path, str, str, Path, str]] = []
    for path in files:
        relative = path.relative_to(source_root).as_posix()
        content = read_text_source(source_root, path)
        source_hash = hashlib.sha256(content).hexdigest()
        key = _fragment_key(content, path)
        fragment_path = fragments_dir / f"{key}.json"
        fragment: dict[str, Any] | None = None
        if fragment_path.is_file():
            try:
                candidate = _json(fragment_path)
                if not validate_fragment(candidate) and candidate.get("source", {}).get("sha256") == source_hash:
                    fragment = candidate
                    cache_hits += 1
                else:
                    corrupt += 1
            except ADWikiError:
                corrupt += 1
        if fragment is None:
            missing.append((path, relative, key, fragment_path, source_hash))
        else:
            fragments_by_path[relative] = fragment
        current_files[relative] = {"fragment": key, "sha256": source_hash}

    if missing:
        if worker_count == 1:
            extracted = [
                _extract_worker(str(source_root), str(item[0])) for item in missing
            ]
        else:
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                extracted = list(
                    executor.map(
                        _extract_worker,
                        [str(source_root)] * len(missing),
                        [str(item[0]) for item in missing],
                    )
                )
        for item, fragment in zip(missing, extracted, strict=True):
            _, relative, _, fragment_path, _ = item
            errors = validate_fragment(fragment)
            if errors:
                raise ADWikiError("structural Fragment validation failed: " + "; ".join(errors))
            _atomic_write(fragment_path, canonical_json_bytes(fragment))
            fragments_by_path[relative] = fragment
            parsed += 1

    graph = build_graph(
        [fragments_by_path[path.relative_to(source_root).as_posix()] for path in files],
        revision=revision,
    )
    graph_bytes = canonical_json_bytes(graph)
    if len(graph_bytes) > MAX_GRAPH_BYTES:
        raise ADWikiError(f"code index graph size {len(graph_bytes)} exceeds limit {MAX_GRAPH_BYTES}")
    graph_hash = hashlib.sha256(graph_bytes).hexdigest()
    graph_relative = f"graphs/{graph_hash}.json"
    graph_path = target / graph_relative
    if not graph_path.exists():
        _atomic_write(graph_path, graph_bytes)

    old_paths = set(old_files)
    current_paths = set(current_files)
    changed = {
        path
        for path in old_paths & current_paths
        if old_files[path].get("sha256") != current_files[path]["sha256"]
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "revision": revision,
        "extractors": {
            "java": "1/tree-sitter-java-0.23.5",
            "maven-xml": "1/stdlib-xml",
            "properties": "1",
        },
        "files": dict(sorted(current_files.items())),
        "graph_file": graph_relative,
        "graph_sha256": graph_hash,
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "ambiguous_edge_count": sum(1 for item in graph["edges"] if item["evidence"] == "AMBIGUOUS"),
        "unsupported": [],
    }
    if fail_before_manifest:
        raise ADWikiError("injected publish failure before manifest")
    _atomic_write(target / "manifest.json", canonical_json_bytes(manifest))
    return {
        "changes": {
            "added": sorted(current_paths - old_paths),
            "changed": sorted(changed),
            "deleted": sorted(old_paths - current_paths),
            "unchanged": sorted((old_paths & current_paths) - changed),
        },
        "graph_sha256": graph_hash,
        "manifest": manifest,
        "metrics": {
            "added": len(current_paths - old_paths),
            "cache_hits": cache_hits,
            "changed": len(changed),
            "corrupt_fragments": corrupt,
            "deleted": len(old_paths - current_paths),
            "parsed": parsed,
            "unchanged": len((old_paths & current_paths) - changed),
        },
        "status": "updated",
    }


def build_or_update_index(
    code_root: str | Path,
    *,
    cache_root: str | Path,
    revision: str,
    workers: int = 1,
    fail_before_manifest: bool = False,
) -> dict[str, Any]:
    target = Path(cache_root).expanduser().resolve()
    with _cache_lock(target):
        return _build_or_update_index_unlocked(
            code_root,
            cache_root=target,
            revision=revision,
            workers=workers,
            fail_before_manifest=fail_before_manifest,
        )
