from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote


PLUGIN_VERSION = "0.3.0"
PROFILE_VERSION = "0.1"
OKF_VERSION = "0.2"

CONCEPT_DIRECTORIES = (
    "sources",
    "entities",
    "concepts",
    "events",
    "syntheses",
    "questions",
    "computations",
    "references",
    "_meta",
)

ALLOWED_STATUS = {"draft", "stable", "deprecated"}
ALLOWED_CONTENT_LANGUAGES = {"en", "zh-CN"}
ALLOWED_OPERATIONS = {"init", "ingest", "query", "writeback", "lint", "migrate"}
ALLOWED_RISKS = {"low", "medium", "high", "prohibited"}
ALLOWED_STATES = {
    "DISCOVERED",
    "PREFLIGHTED",
    "PLANNED",
    "APPROVED",
    "AUTO_APPROVED",
    "REVIEW_REQUIRED",
    "APPLIED",
    "VALIDATED",
    "REVIEWED",
    "COMMITTED",
    "FAILED",
}
STATE_TRANSITIONS = {
    "DISCOVERED": {"PREFLIGHTED", "FAILED"},
    "PREFLIGHTED": {"PLANNED", "FAILED"},
    "PLANNED": {"APPROVED", "AUTO_APPROVED", "REVIEW_REQUIRED", "FAILED"},
    "REVIEW_REQUIRED": {"APPROVED", "FAILED"},
    "APPROVED": {"APPLIED", "FAILED"},
    "AUTO_APPROVED": {"APPLIED", "FAILED"},
    "APPLIED": {"VALIDATED", "FAILED"},
    "VALIDATED": {"REVIEWED", "FAILED"},
    "REVIEWED": {"COMMITTED", "FAILED"},
    "COMMITTED": set(),
    "FAILED": set(),
}

TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]*(.*))?$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
FOOTNOTE = re.compile(r"\[\^([^\]]+)\]")
HUMAN_ACTOR = re.compile(r"human:[^\s:]+")

LANGUAGE_TEXT = {
    "en": {
        "concepts": "Concepts",
        "directories": "Directories",
        "domain_body": (
            "Record only domain-specific terminology, page granularity, and review rules here.\n"
            "The installed AD-Wiki Plugin owns the reusable workflow.\n"
        ),
        "domain_label": "Domain",
        "domain_title": "Domain Overlay",
        "empty_index": "No Concepts in this directory.",
        "index_hint": "Run the AD-Wiki index builder after adding Concepts.",
        "index_title": "Knowledge Bundle Index",
        "log_title": "Knowledge Bundle Update Log",
    },
    "zh-CN": {
        "concepts": "概念",
        "directories": "目录",
        "domain_body": (
            "这里只记录领域术语、页面粒度和评审规则。\n"
            "可复用工作流由已安装的 AD-Wiki Plugin 提供。\n"
        ),
        "domain_label": "领域",
        "domain_title": "领域配置",
        "empty_index": "本目录暂无概念。",
        "index_hint": "添加概念后运行 AD-Wiki 索引构建器。",
        "index_title": "知识包索引",
        "log_title": "知识包更新日志",
    },
}


class ADWikiError(RuntimeError):
    """Raised when an AD-Wiki operation cannot proceed safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _repository_root(repo: str | os.PathLike[str]) -> Path:
    root = Path(repo).expanduser().resolve()
    if root.name == ".git" or ".git" in root.parts:
        raise ADWikiError("repository root cannot be inside .git")
    return root


def _resolve_inside(root: Path, candidate: str | os.PathLike[str], label: str) -> Path:
    raw = Path(candidate).expanduser()
    resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if not _path_is_within(resolved, root):
        raise ADWikiError(f"{label} resolves outside repository: {candidate}")
    return resolved


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new_or_equal(path: Path, content: str, created: list[str], root: Path) -> None:
    if path.exists():
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise ADWikiError(f"refusing to overwrite non-identical file: {_relative_posix(path, root)}")
        return
    _atomic_write_text(path, content)
    created.append(_relative_posix(path, root))


def _content_language(config: dict[str, Any]) -> str:
    value = config.get("content_language", "zh-CN")
    if not isinstance(value, str) or value not in ALLOWED_CONTENT_LANGUAGES:
        raise ADWikiError(
            "content_language must be one of: " + ", ".join(sorted(ALLOWED_CONTENT_LANGUAGES))
        )
    return str(value)


def _normalize_owners(owners: Iterable[str] | None) -> list[str]:
    if owners is None:
        return []
    if isinstance(owners, (str, bytes)):
        raise ADWikiError("review owners must be a list of human:<id> values")
    try:
        values = list(owners)
    except TypeError as exc:
        raise ADWikiError("review owners must be a list of human:<id> values") from exc
    if not all(isinstance(item, str) and HUMAN_ACTOR.fullmatch(item) for item in values):
        raise ADWikiError("review owners must be a list of human:<id> values")
    return sorted(set(values))


def _default_config(domain: str, content_language: str, owners: list[str]) -> dict[str, Any]:
    return {
        "bundle_root": "wiki",
        "content_language": content_language,
        "domain": {
            "concept_types": [
                "Source Summary",
                "Entity",
                "Concept",
                "Synthesis",
                "Decision",
                "Open Question",
                "Attested Computation",
            ],
            "name": domain,
        },
        "ingest": {"default_status": "draft", "max_batch_size": 1, "mode": "supervised"},
        "lint": {
            "broken_links": "warning",
            "missing_claim_source": "error",
            "orphan_pages": "warning",
            "stale_content": "warning",
        },
        "profile_version": PROFILE_VERSION,
        "raw_root": "raw",
        "review": {"high_risk": "pre_apply", "medium_risk": "post_apply", "owners": owners},
        "search": {"mcp_threshold_pages": 1000, "provider": "builtin"},
    }


def _root_index(content_language: str) -> str:
    labels = LANGUAGE_TEXT[content_language]
    return (
        "---\n"
        f'okf_version: "{OKF_VERSION}"\n'
        "---\n\n"
        f"# {labels['index_title']}\n\n"
        f"## {labels['directories']}\n\n"
        f"_{labels['index_hint']}_\n"
    )


def initialize_repository(
    repo: str | os.PathLike[str],
    domain: str = "general",
    content_language: str = "zh-CN",
    owners: Iterable[str] | None = None,
) -> dict[str, Any]:
    root = _repository_root(repo)
    if not domain.strip():
        raise ADWikiError("domain must be non-empty")
    if not isinstance(content_language, str) or content_language not in ALLOWED_CONTENT_LANGUAGES:
        raise ADWikiError(
            "content_language must be one of: " + ", ".join(sorted(ALLOWED_CONTENT_LANGUAGES))
        )
    normalized_owners = _normalize_owners(owners)
    root.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    config_text = json.dumps(
        _default_config(domain.strip(), content_language, normalized_owners),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    registry_text = json.dumps({"sources": [], "version": 1}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    labels = LANGUAGE_TEXT[content_language]
    domain_text = (
        f"# {labels['domain_title']}\n\n"
        f"{labels['domain_label']}: {domain.strip()}\n\n"
        f"{labels['domain_body']}"
    )
    files = {
        "ad-wiki.yaml": config_text,
        ".ad-wiki/.gitignore": "lock\n",
        ".ad-wiki/domain.md": domain_text,
        ".ad-wiki/source-registry.json": registry_text,
        "wiki/index.md": _root_index(content_language),
        "wiki/log.md": f"# {labels['log_title']}\n",
    }
    for relative in [*files, "raw", "wiki", ".ad-wiki"]:
        candidate = root / relative
        if candidate.is_symlink() or not _path_is_within(candidate.resolve(), root):
            raise ADWikiError(f"initialization path escapes repository or uses a symlink: {relative}")
    for relative, content in files.items():
        path = root / relative
        if path.exists() and (not path.is_file() or path.read_text(encoding="utf-8") != content):
            raise ADWikiError(f"refusing to overwrite non-identical file: {relative}")

    directories = [
        "raw/inbox",
        "raw/sources",
        "raw/assets",
        ".ad-wiki/runs",
        *(f"wiki/{name}" for name in CONCEPT_DIRECTORIES),
    ]
    for relative in directories:
        candidate = root / relative
        if candidate.is_symlink() or not _path_is_within(candidate.resolve(), root):
            raise ADWikiError(f"initialization path escapes repository or uses a symlink: {relative}")
    for relative in directories:
        (root / relative).mkdir(parents=True, exist_ok=True)

    for relative, content in files.items():
        _write_new_or_equal(root / relative, content, created, root)

    warnings = []
    if not normalized_owners:
        warnings.append(
            "尚未配置 review.owners；高风险事务已禁用，请在 ad-wiki.yaml 中添加 human:<id>。"
            if content_language == "zh-CN"
            else "review.owners is empty; high-risk transactions are disabled until ad-wiki.yaml lists a human:<id>."
        )
    return {
        "created": sorted(created),
        "repository": str(root),
        "status": "created" if created else "unchanged",
        "warnings": warnings,
    }


def _load_config(root: Path) -> dict[str, Any]:
    path = root / "ad-wiki.yaml"
    if path.is_symlink() or not _path_is_within(path.resolve(), root):
        raise ADWikiError("ad-wiki.yaml must not escape the repository or use a symlink")
    if not path.is_file():
        raise ADWikiError("ad-wiki.yaml not found; initialize the repository first")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ADWikiError(f"ad-wiki.yaml must use the AD-Wiki JSON-compatible YAML profile: {exc}") from exc
    if not isinstance(value, dict):
        raise ADWikiError("ad-wiki.yaml must contain a mapping")
    return value


def _configured_roots(root: Path) -> tuple[Path, Path, dict[str, Any]]:
    config = _load_config(root)
    raw = _resolve_inside(root, str(config.get("raw_root", "raw")), "raw_root")
    bundle = _resolve_inside(root, str(config.get("bundle_root", "wiki")), "bundle_root")
    return raw, bundle, config


def _require_supported_profile(config: dict[str, Any]) -> None:
    if str(config.get("profile_version", "")) != PROFILE_VERSION:
        raise ADWikiError(
            f"unsupported profile_version; expected {PROFILE_VERSION}; use the Migrate workflow"
        )


def _load_registry(root: Path) -> dict[str, Any]:
    path = root / ".ad-wiki/source-registry.json"
    if path.is_symlink() or not _path_is_within(path.resolve(), root):
        raise ADWikiError("source registry must not escape the repository or use a symlink")
    if not path.is_file():
        raise ADWikiError("source registry not found; initialize the repository first")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ADWikiError(f"invalid source registry: {exc}") from exc
    if not isinstance(registry, dict) or registry.get("version") != 1 or not isinstance(registry.get("sources"), list):
        raise ADWikiError("unsupported source registry format")
    required = {
        "canonical_locator": str,
        "path": str,
        "registered_at": str,
        "sha256": str,
        "source_id": str,
        "version": int,
    }
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    seen_versions: set[tuple[str, int]] = set()
    for index, record in enumerate(registry["sources"]):
        valid = isinstance(record, dict) and all(
            key in record and type(record[key]) is expected_type
            for key, expected_type in required.items()
        )
        if not valid:
            raise ADWikiError(f"malformed source registry record at index {index}")
        path = record["path"]
        locator = record["canonical_locator"]
        source_id = record["source_id"]
        version = record["version"]
        if (
            not path
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or not locator
            or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
            or not re.fullmatch(r"SRC-[A-F0-9]{12}", source_id)
            or version < 1
            or ("author" in record and not isinstance(record["author"], str))
        ):
            raise ADWikiError(f"malformed source registry record at index {index}")
        locator_version = (locator, version)
        if path in seen_paths or source_id in seen_ids or locator_version in seen_versions:
            raise ADWikiError(f"duplicate source registry identity at index {index}")
        seen_paths.add(path)
        seen_ids.add(source_id)
        seen_versions.add(locator_version)
    return registry


def register_source(
    repo: str | os.PathLike[str],
    source: str | os.PathLike[str],
    canonical_locator: str,
    author: str | None = None,
) -> dict[str, Any]:
    root = _repository_root(repo)
    raw_root, _, config = _configured_roots(root)
    _require_supported_profile(config)
    source_path = _resolve_inside(root, source, "source")
    if not _path_is_within(source_path, raw_root):
        raise ADWikiError("source must resolve inside raw")
    if not source_path.is_file():
        raise ADWikiError(f"source is not a regular file: {_relative_posix(source_path, root)}")
    if not canonical_locator.strip():
        raise ADWikiError("canonical locator must be non-empty")

    relative = _relative_posix(source_path, root)
    digest = _sha256_file(source_path)
    registry = _load_registry(root)
    records: list[dict[str, Any]] = registry["sources"]

    for record in records:
        if record["path"] == relative:
            if record["sha256"] != digest:
                raise ADWikiError(f"registered Raw source changed: {relative}")
            if record["canonical_locator"] != canonical_locator.strip():
                raise ADWikiError(f"registered path already belongs to another canonical locator: {relative}")
            return {"record": record, "status": "unchanged"}

    for record in records:
        if record["canonical_locator"] == canonical_locator.strip() and record["sha256"] == digest:
            return {"record": record, "status": "unchanged"}

    for record in records:
        if record["sha256"] == digest:
            raise ADWikiError(
                f"duplicate source content already registered as {record['source_id']}"
            )

    versions = [record["version"] for record in records if record["canonical_locator"] == canonical_locator.strip()]
    record: dict[str, Any] = {
        "canonical_locator": canonical_locator.strip(),
        "path": relative,
        "registered_at": _utc_now(),
        "sha256": digest,
        "source_id": f"SRC-{digest[:12].upper()}",
        "version": max(versions, default=0) + 1,
    }
    if author:
        record["author"] = author
    records.append(record)
    records.sort(key=lambda item: (item["canonical_locator"], item["version"], item["path"]))
    _atomic_write_json(root / ".ad-wiki/source-registry.json", registry)
    return {"record": record, "status": "registered"}


def guard_raw(repo: str | os.PathLike[str]) -> dict[str, Any]:
    root = _repository_root(repo)
    raw_root, _, _ = _configured_roots(root)
    registry = _load_registry(root)
    violations: list[dict[str, str]] = []
    checked = 0

    for record in registry["sources"]:
        relative = record.get("path", "")
        unresolved = root / relative
        if not unresolved.exists():
            violations.append({"code": "ADW-E300", "message": "registered Raw source is missing", "path": relative})
            continue
        resolved = unresolved.resolve()
        if not _path_is_within(resolved, raw_root):
            violations.append({"code": "ADW-E302", "message": "registered Raw source escapes raw_root", "path": relative})
            continue
        if not resolved.is_file():
            violations.append({"code": "ADW-E303", "message": "registered Raw source is not a file", "path": relative})
            continue
        checked += 1
        actual = _sha256_file(resolved)
        if actual != record.get("sha256"):
            violations.append({"code": "ADW-E301", "message": "registered Raw source hash changed", "path": relative})

    return {"checked": checked, "ok": not violations, "violations": violations}


def _unquote_scalar(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped[0:1] == stripped[-1:] and stripped.startswith(("\"", "'")):
        return stripped[1:-1]
    return stripped


def _frontmatter(text: str) -> tuple[list[str], str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return None
    return lines[1:end], "\n".join(lines[end + 1 :])


def _top_level(lines: list[str]) -> tuple[dict[str, str | None], set[str], list[str]]:
    fields: dict[str, str | None] = {}
    duplicates: set[str] = set()
    malformed: list[str] = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            malformed.append(line)
            continue
        if line[0].isspace() or line.lstrip().startswith("-"):
            continue
        match = TOP_LEVEL_KEY.match(line)
        if not match:
            malformed.append(line)
            continue
        key, value = match.groups()
        if _unquote_scalar(value) in {"|", ">", "|-", ">-", "|+", ">+"}:
            malformed.append(line)
            continue
        if key in fields:
            duplicates.add(key)
        fields[key] = _unquote_scalar(value)
    return fields, duplicates, malformed


def _block(lines: list[str], key: str) -> list[str]:
    start: int | None = None
    for index, line in enumerate(lines):
        match = TOP_LEVEL_KEY.match(line) if line and not line[0].isspace() else None
        if match and match.group(1) == key:
            start = index + 1
            break
    if start is None:
        return []
    result: list[str] = []
    for line in lines[start:]:
        if line and not line[0].isspace() and TOP_LEVEL_KEY.match(line):
            break
        result.append(line)
    return result


def _nested_scalar(lines: list[str], key: str) -> str | None:
    pattern = re.compile(rf"^\s+(?:-\s+)?{re.escape(key)}:\s*(.+?)\s*$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return _unquote_scalar(match.group(1))
    return None


def _inline_scalar(value: str | None, key: str) -> str | None:
    if not value or not value.startswith("{"):
        return None
    match = re.search(rf"(?:^|[,{{])\s*{re.escape(key)}\s*:\s*([^,}}]+)", value)
    return _unquote_scalar(match.group(1)) if match else None


def _source_entries(lines: list[str], inline_value: str | None) -> list[dict[str, str]]:
    if inline_value and inline_value.startswith("["):
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in _block(lines, "sources"):
        item = re.match(r"^\s+-\s+([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*$", line)
        nested = re.match(r"^\s+([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*$", line)
        if item:
            if current is not None:
                entries.append(current)
            current = {item.group(1): _unquote_scalar(item.group(2)) or ""}
        elif nested and current is not None:
            current[nested.group(1)] = _unquote_scalar(nested.group(2)) or ""
    if current is not None:
        entries.append(current)
    return entries


def _verified_entries(lines: list[str], inline_value: str | None) -> list[dict[str, str]] | None:
    if inline_value:
        mappings = re.findall(r"\{([^{}]+)\}", inline_value)
        if inline_value.startswith("{") and inline_value.endswith("}"):
            mappings = [inline_value[1:-1]]
        if not mappings:
            return None
        return [
            {
                key: value
                for key in ("by", "at")
                if (value := _inline_scalar("{" + mapping + "}", key)) is not None
            }
            for mapping in mappings
        ]

    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in _block(lines, "verified"):
        inline_item = re.match(r"^\s+-\s+\{(.+)\}\s*$", line)
        item = re.match(r"^\s+-\s+([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*$", line)
        nested = re.match(r"^\s+([A-Za-z_][A-Za-z0-9_-]*):\s*(.+?)\s*$", line)
        if inline_item:
            if current is not None:
                entries.append(current)
                current = None
            mapping = "{" + inline_item.group(1) + "}"
            entries.append(
                {
                    key: value
                    for key in ("by", "at")
                    if (value := _inline_scalar(mapping, key)) is not None
                }
            )
        elif item:
            if current is not None:
                entries.append(current)
            current = {item.group(1): _unquote_scalar(item.group(2)) or ""}
        elif nested:
            if current is None:
                current = {}
            current[nested.group(1)] = _unquote_scalar(nested.group(2)) or ""
        elif line.strip():
            return None
    if current is not None:
        entries.append(current)
    return entries


def _bundle_markdown_files(bundle: Path) -> tuple[list[Path], list[Path]]:
    safe: list[Path] = []
    unsafe: list[Path] = []
    for path in sorted(bundle.rglob("*.md")):
        if path.is_symlink() or not _path_is_within(path.resolve(), bundle):
            unsafe.append(path)
        elif path.is_file():
            safe.append(path)
    return safe, unsafe


def _concept_files(bundle: Path) -> list[Path]:
    markdown, unsafe = _bundle_markdown_files(bundle)
    if unsafe:
        paths = ", ".join(path.relative_to(bundle).as_posix() for path in unsafe)
        raise ADWikiError(f"Markdown path escapes Bundle or uses a symlink: {paths}")
    return [
        path
        for path in markdown
        if path.name not in {"index.md", "log.md"}
        and not any(part.startswith(".") for part in path.relative_to(bundle).parts)
    ]


def _concept_metadata(path: Path) -> dict[str, str]:
    parsed = _frontmatter(path.read_text(encoding="utf-8"))
    if not parsed:
        return {"description": "", "title": path.stem.replace("-", " ").title(), "type": "Unknown"}
    fields, _, _ = _top_level(parsed[0])
    return {
        "description": fields.get("description") or "",
        "title": fields.get("title") or path.stem.replace("-", " ").title(),
        "type": fields.get("type") or "Unknown",
    }


def _index_content(directory: Path, bundle: Path, content_language: str) -> str:
    labels = LANGUAGE_TEXT[content_language]
    root = directory == bundle
    title = labels["index_title"] if root else (
        f"{directory.name.replace('-', ' ').title()} Index"
        if content_language == "en"
        else f"{directory.name} 索引"
    )
    parts: list[str] = []
    if root:
        parts.append(f'---\nokf_version: "{OKF_VERSION}"\n---\n')
    parts.append(f"# {title}\n")

    concepts = sorted(
        (path for path in directory.glob("*.md") if path.name not in {"index.md", "log.md"}),
        key=lambda path: path.name.casefold(),
    )
    subdirs = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_dir() and not path.name.startswith(".") and any(path.rglob("*.md"))
        ),
        key=lambda path: path.name.casefold(),
    )

    if concepts:
        parts.append(f"## {labels['concepts']}\n")
        for concept in concepts:
            metadata = _concept_metadata(concept)
            target = "/" + concept.relative_to(bundle).as_posix()
            suffix = f" - {metadata['description']}" if metadata["description"] else ""
            parts.append(f"* [{metadata['title']}]({target}){suffix}")
        parts.append("")
    if subdirs:
        parts.append(f"## {labels['directories']}\n")
        for subdir in subdirs:
            target = "/" + subdir.relative_to(bundle).as_posix().rstrip("/") + "/"
            parts.append(f"* [{subdir.name}]({target})")
        parts.append("")
    if not concepts and not subdirs:
        parts.append(f"_{labels['empty_index']}_\n")
    return "\n".join(parts).rstrip() + "\n"


def build_indexes(repo: str | os.PathLike[str]) -> dict[str, Any]:
    root = _repository_root(repo)
    _, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    content_language = _content_language(config)
    root_index = bundle / "index.md"
    if root_index.is_file():
        parsed = _frontmatter(root_index.read_text(encoding="utf-8"))
        if parsed:
            fields, _, _ = _top_level(parsed[0])
            declared = fields.get("okf_version")
            if declared and declared != OKF_VERSION:
                raise ADWikiError(
                    f"unsupported OKF version {declared}; expected {OKF_VERSION}; use the Migrate workflow"
                )
    bundle.mkdir(parents=True, exist_ok=True)
    directories = {bundle}
    for concept in _concept_files(bundle):
        directories.add(concept.parent)
        parent = concept.parent
        while parent != bundle:
            parent = parent.parent
            directories.add(parent)

    changed: list[str] = []
    for directory in sorted(directories, key=lambda item: item.relative_to(bundle).as_posix()):
        content = _index_content(directory, bundle, content_language)
        path = directory / "index.md"
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            _atomic_write_text(path, content)
            changed.append(_relative_posix(path, root))
    return {"changed": changed, "count": len(directories), "status": "updated" if changed else "unchanged"}


def _issue(code: str, message: str, path: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "path": path, **extra}


def _lint_severities(config: dict[str, Any], errors: list[dict[str, Any]]) -> dict[str, str]:
    defaults = {
        "broken_links": "warning",
        "missing_claim_source": "error",
        "orphan_pages": "warning",
        "stale_content": "warning",
    }
    lint = config.get("lint", {})
    if not isinstance(lint, dict):
        errors.append(_issue("ADW-E107", "lint configuration must be a mapping", "ad-wiki.yaml"))
        return defaults
    result: dict[str, str] = {}
    for key, default in defaults.items():
        value = lint.get(key, default)
        if value not in {"error", "warning", "ignore"}:
            errors.append(
                _issue(
                    "ADW-E107",
                    f"lint.{key} must be error, warning, or ignore",
                    "ad-wiki.yaml",
                )
            )
            value = default
        result[key] = value
    return result


def _append_policy_finding(
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    severity: str,
    warning_code: str,
    message: str,
    path: str,
) -> None:
    if severity == "ignore":
        return
    code = warning_code if severity == "warning" else warning_code.replace("ADW-W", "ADW-E", 1)
    target = warnings if severity == "warning" else errors
    target.append(_issue(code, message, path))


def _local_link_target(link: str) -> str | None:
    candidate = link.strip().split()[0].strip("<>")
    if not candidate or candidate.startswith(("http://", "https://", "mailto:", "urn:", "#")):
        return None
    return unquote(candidate.split("#", 1)[0].split("?", 1)[0])


def validate_repository(repo: str | os.PathLike[str], today: date | None = None) -> dict[str, Any]:
    root = _repository_root(repo)
    raw_root, bundle, config = _configured_roots(root)
    current_date = today or date.today()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    info: list[dict[str, Any]] = []
    lint_severities = _lint_severities(config, errors)
    domain = config.get("domain", {})
    configured_types: set[str] | None = None
    if not isinstance(domain, dict):
        errors.append(_issue("ADW-E108", "domain configuration must be a mapping", "ad-wiki.yaml"))
    else:
        raw_types = domain.get("concept_types")
        if not isinstance(raw_types, list) or not raw_types or not all(
            isinstance(item, str) and item.strip() for item in raw_types
        ):
            errors.append(
                _issue(
                    "ADW-E108",
                    "domain.concept_types must be a non-empty list of strings",
                    "ad-wiki.yaml",
                )
            )
        else:
            configured_types = {item.strip() for item in raw_types}
        if not isinstance(domain.get("name"), str) or not domain.get("name", "").strip():
            errors.append(_issue("ADW-E108", "domain.name must be a non-empty string", "ad-wiki.yaml"))

    ingest_config = config.get("ingest", {})
    if not isinstance(ingest_config, dict):
        errors.append(_issue("ADW-E109", "ingest configuration must be a mapping", "ad-wiki.yaml"))
    else:
        if ingest_config.get("mode", "supervised") != "supervised":
            errors.append(_issue("ADW-E109", "MVP ingest.mode must be supervised", "ad-wiki.yaml"))
        max_batch_size = ingest_config.get("max_batch_size", 1)
        if type(max_batch_size) is not int or max_batch_size < 1:
            errors.append(_issue("ADW-E109", "ingest.max_batch_size must be a positive integer", "ad-wiki.yaml"))
        if ingest_config.get("default_status", "draft") not in ALLOWED_STATUS:
            errors.append(_issue("ADW-E109", "ingest.default_status must be a supported status", "ad-wiki.yaml"))

    content_language = config.get("content_language", "zh-CN")
    if not isinstance(content_language, str) or content_language not in ALLOWED_CONTENT_LANGUAGES:
        errors.append(
            _issue(
                "ADW-E109",
                "content_language must be one of: " + ", ".join(sorted(ALLOWED_CONTENT_LANGUAGES)),
                "ad-wiki.yaml",
            )
        )

    review_config = config.get("review", {})
    if not isinstance(review_config, dict):
        errors.append(_issue("ADW-E109", "review configuration must be a mapping", "ad-wiki.yaml"))
    else:
        if review_config.get("medium_risk", "post_apply") != "post_apply":
            errors.append(_issue("ADW-E109", "review.medium_risk must be post_apply", "ad-wiki.yaml"))
        if review_config.get("high_risk", "pre_apply") != "pre_apply":
            errors.append(_issue("ADW-E109", "review.high_risk must be pre_apply", "ad-wiki.yaml"))
        owners = review_config.get("owners", [])
        if not isinstance(owners, list) or not all(
            isinstance(item, str) and HUMAN_ACTOR.fullmatch(item) for item in owners
        ):
            errors.append(_issue("ADW-E109", "review.owners must be a list of human:<id> values", "ad-wiki.yaml"))

    search_config = config.get("search", {})
    if not isinstance(search_config, dict):
        errors.append(_issue("ADW-E109", "search configuration must be a mapping", "ad-wiki.yaml"))
    else:
        if search_config.get("provider", "builtin") != "builtin":
            errors.append(_issue("ADW-E109", "MVP search.provider must be builtin", "ad-wiki.yaml"))
        threshold = search_config.get("mcp_threshold_pages", 1000)
        if type(threshold) is not int or threshold < 1:
            errors.append(_issue("ADW-E109", "search.mcp_threshold_pages must be positive", "ad-wiki.yaml"))
    if not raw_root.is_dir():
        errors.append(_issue("ADW-E100", "raw_root must be an existing directory", _relative_posix(raw_root, root)))
    if not bundle.is_dir():
        errors.append(_issue("ADW-E100", "bundle_root must be an existing directory", _relative_posix(bundle, root)))
    if raw_root == bundle or _path_is_within(raw_root, bundle) or _path_is_within(bundle, raw_root):
        errors.append(_issue("ADW-E106", "raw_root and bundle_root must not overlap", "ad-wiki.yaml"))
    if str(config.get("profile_version", "")) != PROFILE_VERSION:
        errors.append(
            _issue(
                "ADW-E105",
                f"unsupported profile_version; expected {PROFILE_VERSION}",
                "ad-wiki.yaml",
            )
        )

    markdown_paths, unsafe_markdown = _bundle_markdown_files(bundle) if bundle.is_dir() else ([], [])
    for path in unsafe_markdown:
        errors.append(
            _issue(
                "ADW-E121",
                "Markdown path escapes Bundle or uses a symlink",
                _relative_posix(path, root),
            )
        )
    concept_paths = [
        path
        for path in markdown_paths
        if path.name not in {"index.md", "log.md"}
        and not any(part.startswith(".") for part in path.relative_to(bundle).parts)
    ]
    inbound: dict[Path, int] = {path.resolve(): 0 for path in concept_paths}

    for concept in concept_paths:
        relative = _relative_posix(concept, root)
        text = concept.read_text(encoding="utf-8")
        parsed = _frontmatter(text)
        if not parsed:
            errors.append(_issue("OKF-E001", "Concept must start with a closed YAML frontmatter block", relative))
            continue
        lines, body = parsed
        fields, duplicates, malformed = _top_level(lines)
        for key in sorted(duplicates):
            errors.append(_issue("OKF-E003", f"duplicate top-level frontmatter key: {key}", relative))
        for line in malformed:
            errors.append(_issue("OKF-E004", f"unsupported or malformed top-level YAML: {line}", relative))
        if not fields.get("type"):
            errors.append(_issue("OKF-E002", "Concept frontmatter requires a non-empty type", relative))
        elif configured_types is not None and fields["type"] not in configured_types:
            warnings.append(
                _issue(
                    "ADW-W250",
                    f"Concept type is not declared by this repository: {fields['type']}",
                    relative,
                )
            )

        status = fields.get("status")
        if status and status not in ALLOWED_STATUS:
            errors.append(_issue("ADW-E101", f"unsupported lifecycle status: {status}", relative))

        generated = fields.get("generated")
        if "generated" in fields:
            generated_by = _inline_scalar(generated, "by") or _nested_scalar(_block(lines, "generated"), "by")
            if not generated_by:
                errors.append(_issue("ADW-E102", "generated requires by", relative))

        stale_after = fields.get("stale_after")
        if stale_after:
            try:
                stale_date = date.fromisoformat(stale_after)
            except ValueError:
                errors.append(_issue("ADW-E104", "stale_after must be YYYY-MM-DD", relative))
            else:
                if current_date >= stale_date:
                    _append_policy_finding(
                        errors,
                        warnings,
                        lint_severities["stale_content"],
                        "ADW-W201",
                        "Concept is stale on or after stale_after",
                        relative,
                    )

        inline_sources = fields.get("sources")
        if inline_sources:
            errors.append(
                _issue(
                    "ADW-E111",
                    "inline sources syntax is unsupported; use an indented sources list",
                    relative,
                )
            )
        source_entries = _source_entries(lines, inline_sources)
        source_ids = {entry.get("id", "") for entry in source_entries if entry.get("id")}
        for entry in source_entries:
            if not entry.get("resource"):
                errors.append(_issue("ADW-E110", "each sources entry requires resource", relative))
        footnotes = set(FOOTNOTE.findall(body))
        for label in sorted(footnotes - source_ids):
            _append_policy_finding(
                errors,
                warnings,
                lint_severities["missing_claim_source"],
                "ADW-W220",
                f"claim footnote has no matching sources id: {label}",
                relative,
            )

        if "verified" in fields:
            verified_entries = _verified_entries(lines, fields.get("verified"))
            if not verified_entries:
                errors.append(_issue("ADW-E112", "verified must contain at least one {by, at} event", relative))
            else:
                for entry in verified_entries:
                    actor = entry.get("by", "")
                    timestamp = entry.get("at", "")
                    actor_valid = bool(
                        re.fullmatch(r"(?:human|process):[^\s:]+|[^\s/:]+/[^\s/]+", actor)
                    )
                    try:
                        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        timestamp_valid = bool(timestamp)
                    except ValueError:
                        timestamp_valid = False
                    if not actor_valid or not timestamp_valid:
                        errors.append(
                            _issue(
                                "ADW-E112",
                                "each verified event requires a valid actor and ISO 8601 at timestamp",
                                relative,
                            )
                        )

        for raw_link in MARKDOWN_LINK.findall(body):
            target_text = _local_link_target(raw_link)
            if target_text is None:
                continue
            target = (bundle / target_text.lstrip("/")).resolve() if target_text.startswith("/") else (concept.parent / target_text).resolve()
            if not _path_is_within(target, bundle):
                errors.append(_issue("ADW-E120", f"link escapes Bundle: {raw_link}", relative))
                continue
            candidate = target / "index.md" if target.is_dir() else target
            if not candidate.exists():
                _append_policy_finding(
                    errors,
                    warnings,
                    lint_severities["broken_links"],
                    "ADW-W210",
                    f"broken local link: {raw_link}",
                    relative,
                )
            elif candidate.resolve() in inbound:
                inbound[candidate.resolve()] += 1

    root_index = bundle / "index.md"
    if root_index not in markdown_paths:
        errors.append(_issue("OKF-E010", "AD-Wiki profile requires a Bundle-root index.md", _relative_posix(root_index, root)))

    for index_path in (path for path in markdown_paths if path.name == "index.md"):
        relative = _relative_posix(index_path, root)
        text = index_path.read_text(encoding="utf-8")
        parsed = _frontmatter(text)
        if index_path == bundle / "index.md":
            if parsed:
                fields, duplicates, malformed = _top_level(parsed[0])
                if duplicates or malformed or set(fields) - {"okf_version"}:
                    errors.append(_issue("OKF-E011", "root index frontmatter may contain only okf_version", relative))
                if fields.get("okf_version") != OKF_VERSION:
                    errors.append(_issue("OKF-E012", f"root index must declare okf_version {OKF_VERSION}", relative))
            else:
                warnings.append(_issue("ADW-W231", "root index does not declare okf_version", relative))
        elif parsed:
            errors.append(_issue("OKF-E013", "nested index.md must not contain frontmatter", relative))

    for directory in {bundle, *(path.parent for path in concept_paths)}:
        index_path = directory / "index.md"
        direct_concepts = [path for path in concept_paths if path.parent == directory]
        if not index_path.is_file():
            if direct_concepts:
                warnings.append(_issue("ADW-W230", "directory with Concepts is missing index.md", _relative_posix(directory, root)))
            continue
        index_body = index_path.read_text(encoding="utf-8")
        for concept in direct_concepts:
            expected = "/" + concept.relative_to(bundle).as_posix()
            if expected not in index_body:
                warnings.append(_issue("ADW-W230", f"index does not list {expected}", _relative_posix(index_path, root)))

    log_path = bundle / "log.md"
    if log_path in markdown_paths:
        headings = re.findall(r"^##\s+(.+?)\s*$", log_path.read_text(encoding="utf-8"), re.MULTILINE)
        dates: list[date] = []
        for heading in headings:
            try:
                dates.append(date.fromisoformat(heading))
            except ValueError:
                errors.append(_issue("OKF-E020", f"log date heading must be YYYY-MM-DD: {heading}", _relative_posix(log_path, root)))
        if dates and dates != sorted(dates, reverse=True):
            errors.append(_issue("OKF-E021", "log date headings must be newest first", _relative_posix(log_path, root)))
    else:
        errors.append(_issue("ADW-E103", "AD-Wiki profile requires a Bundle-root log.md", _relative_posix(log_path, root)))

    for concept, count in sorted(inbound.items(), key=lambda item: str(item[0])):
        if count == 0:
            _append_policy_finding(
                errors,
                warnings,
                lint_severities["orphan_pages"],
                "ADW-W240",
                "Concept has no inbound Concept links",
                _relative_posix(concept, root),
            )

    raw_report = guard_raw(root)
    errors.extend(raw_report["violations"])
    info.append(_issue("ADW-I001", f"validated {len(concept_paths)} Concepts", _relative_posix(bundle, root)))
    return {"errors": errors, "info": info, "ok": not errors, "warnings": warnings}


def _validate_run_paths(root: Path, values: Iterable[str], field: str) -> list[str]:
    result: list[str] = []
    for value in values:
        if Path(value).is_absolute():
            raise ADWikiError(f"{field} path resolves outside repository: {value}")
        resolved = _resolve_inside(root, value, f"{field} path")
        result.append(_relative_posix(resolved, root))
    return result


def write_run_report(
    repo: str | os.PathLike[str],
    *,
    run_id: str,
    operation: str,
    state: str,
    risk: str,
    inputs: Iterable[str],
    read_set: Iterable[str],
    write_set: Iterable[str],
    validations: list[dict[str, Any]],
) -> dict[str, Any]:
    root = _repository_root(repo)
    _, _, config = _configured_roots(root)
    if not RUN_ID.fullmatch(run_id) or ".." in run_id:
        raise ADWikiError(f"invalid run id: {run_id}")
    if operation not in ALLOWED_OPERATIONS:
        raise ADWikiError(f"unsupported operation: {operation}")
    if state not in ALLOWED_STATES:
        raise ADWikiError(f"unsupported state: {state}")
    if risk not in ALLOWED_RISKS:
        raise ADWikiError(f"unsupported risk: {risk}")
    if risk == "prohibited":
        raise ADWikiError("prohibited operations cannot be recorded as runnable")

    runs_root = root / ".ad-wiki/runs"
    if runs_root.is_symlink() or not _path_is_within(runs_root.resolve(), root):
        raise ADWikiError(".ad-wiki/runs must not escape the repository or use a symlink")
    run_directory = runs_root / run_id
    if run_directory.is_symlink() or not _path_is_within(run_directory.resolve(), root):
        raise ADWikiError("run directory must not escape the repository or use a symlink")
    path = run_directory / "run.json"
    previous: dict[str, Any] | None = None
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("operation") != operation:
            raise ADWikiError("run operation cannot change")
        if previous.get("risk") != risk:
            raise ADWikiError("run risk cannot change")
        previous_state = previous.get("status")
        if state != previous_state and state not in STATE_TRANSITIONS.get(previous_state, set()):
            raise ADWikiError(f"invalid state transition: {previous_state} -> {state}")
    elif state not in {"DISCOVERED", "PREFLIGHTED", "PLANNED"}:
        raise ADWikiError(f"new run cannot start at state: {state}")

    if state in {"VALIDATED", "REVIEWED", "COMMITTED"}:
        if not validations or any(item.get("status") != "passed" for item in validations):
            raise ADWikiError(f"{state} requires non-empty passed validation evidence")

    now = _utc_now()
    report = {
        "created_at": previous.get("created_at", now) if previous else now,
        "inputs": _validate_run_paths(root, inputs, "input"),
        "operation": operation,
        "plugin_version": PLUGIN_VERSION,
        "profile_version": str(config.get("profile_version", PROFILE_VERSION)),
        "read_set": _validate_run_paths(root, read_set, "read_set"),
        "risk": risk,
        "run_id": run_id,
        "status": state,
        "updated_at": now,
        "validations": validations,
        "write_set": _validate_run_paths(root, write_set, "write_set"),
    }
    _atomic_write_json(path, report)
    return report
