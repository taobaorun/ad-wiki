from __future__ import annotations

import hashlib
import ctypes
import errno
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .core import (
    ADWikiError,
    OKF_VERSION,
    PLUGIN_VERSION,
    PROFILE_VERSION,
    STATIC_AGENT_FILES,
    _configured_roots,
    _frontmatter,
    _load_registry,
    _path_is_within,
    _require_supported_profile,
    _sha256_file,
    _source_entries,
    _top_level,
    guard_raw,
    validate_repository,
)


DELIVERY_TEMPLATE_VERSION = "1"
OUTPUT_FORMATS = {"both", "directory", "zip"}
MAX_INCLUDED_FILES = 100_000
MAX_PATH_BYTES = 1_024
EXCLUDED_PATHS = [".ad-wiki/runs", ".ad-wiki/cache", ".ad-wiki/lock"]
REVIEWABLE_WARNING_CODES = {"ADW-W201", "ADW-W240", "ADW-W260"}
DENIED_NAMES = {".env", "id_dsa", "id_ed25519", "id_rsa"}
DENIED_SUFFIXES = {".der", ".jks", ".key", ".p12", ".pfx", ".pem"}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
)
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
VALID_WIKI_NAME = re.compile(r"^[A-Za-z0-9 _-]+$")
SAFE_CONFIGURED_ROOT = re.compile(r"^[A-Za-z0-9._/-]+$")
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = PLUGIN_ROOT / "skills/ad-wiki-ship/assets/delivered-skill"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def canonical_skill_name(wiki_name: str) -> str:
    if (
        not isinstance(wiki_name, str)
        or not wiki_name.strip()
        or not VALID_WIKI_NAME.fullmatch(wiki_name)
    ):
        raise ADWikiError(
            "wiki name may contain only ASCII letters, digits, spaces, underscores, and hyphens"
        )
    normalized = re.sub(r"[ _-]+", "-", wiki_name.strip().lower()).strip("-")
    skill_name = f"ad-{normalized}"
    if not normalized or len(skill_name) > 63:
        raise ADWikiError(
            "generated Skill name must contain 1 to 60 identity characters and be at most 63 characters"
        )
    return skill_name


def render_delivery_template(template: str, values: dict[str, str]) -> str:
    placeholders = set(PLACEHOLDER.findall(template))
    supplied = set(values)
    if placeholders != supplied:
        missing = sorted(placeholders - supplied)
        extra = sorted(supplied - placeholders)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        raise ADWikiError(
            "delivery template variables do not match: " + "; ".join(detail)
        )
    rendered = PLACEHOLDER.sub(lambda match: values[match.group(1)], template)
    if PLACEHOLDER.search(rendered):
        raise ADWikiError("delivery template contains unresolved placeholders")
    return rendered


def _safe_configured_root(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or Path(value).is_absolute()
        or ".." in Path(value).parts
        or not SAFE_CONFIGURED_ROOT.fullmatch(value)
    ):
        raise ADWikiError(f"{label} must use a safe relative path for Skill delivery")
    return value


def _has_symlink_component(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_regular_file(root: Path, path: Path, relative: str) -> None:
    if len(relative.encode("utf-8")) > MAX_PATH_BYTES:
        raise ADWikiError(f"included path exceeds {MAX_PATH_BYTES} bytes: {relative}")
    if _has_symlink_component(path, root):
        raise ADWikiError(f"included path uses a symlink: {relative}")
    try:
        mode = path.stat(follow_symlinks=False).st_mode
    except FileNotFoundError as exc:
        raise ADWikiError(f"included file is missing: {relative}") from exc
    if not stat.S_ISREG(mode):
        raise ADWikiError(f"included path is not a regular file: {relative}")
    if not _path_is_within(path.resolve(), root):
        raise ADWikiError(f"included path escapes repository: {relative}")


def _bundle_files(root: Path, bundle: Path) -> list[Path]:
    files: list[Path] = []
    for directory, directory_names, file_names in os.walk(bundle, followlinks=False):
        current = Path(directory)
        for name in list(directory_names):
            candidate = current / name
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                raise ADWikiError(f"Bundle directory uses a symlink: {relative}")
        for name in file_names:
            path = current / name
            relative = path.relative_to(root).as_posix()
            _safe_regular_file(root, path, relative)
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _concept_inventory(bundle: Path) -> list[Path]:
    return [
        path
        for path in sorted(bundle.rglob("*.md"))
        if path.name not in {"index.md", "log.md"}
        and not any(part.startswith(".") for part in path.relative_to(bundle).parts)
    ]


def _registered_match(
    root: Path,
    concept: Path,
    entry: dict[str, str],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resource = entry.get("resource", "")
    source_id = entry.get("id", "")
    locator_matches = [
        record for record in records if resource == record["canonical_locator"]
    ]
    if locator_matches:
        return [max(locator_matches, key=lambda record: int(record["version"]))]
    if resource and "://" not in resource and not resource.startswith("git@"):
        candidate = (concept.parent / resource).resolve()
        path_matches = [
            record
            for record in records
            if candidate == (root / record["path"]).resolve()
        ]
        if path_matches:
            return path_matches
    return [record for record in records if source_id == record["source_id"]]


def _external_sources(
    root: Path,
    bundle: Path,
    concepts: Iterable[Path],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    external: dict[str, dict[str, set[str]]] = {}
    for concept in concepts:
        parsed = _frontmatter(concept.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        lines, _ = parsed
        fields, _, _ = _top_level(lines)
        concept_id = concept.relative_to(bundle).with_suffix("").as_posix()
        for entry in _source_entries(lines, fields.get("sources")):
            matches = _registered_match(root, concept, entry, records)
            if len(matches) > 1:
                raise ADWikiError(
                    f"Concept source resolves to multiple registry records: {concept.relative_to(root).as_posix()}"
                )
            if matches:
                continue
            resource = entry.get("resource", "")
            if not resource:
                continue
            if not re.match(
                r"^[A-Za-z][A-Za-z0-9+.-]*:", resource
            ) and not resource.startswith("git@"):
                raise ADWikiError(
                    "Concept declares an unregistered local source: "
                    + concept.relative_to(root).as_posix()
                )
            item = external.setdefault(
                resource, {"source_ids": set(), "concepts": set()}
            )
            if entry.get("id"):
                item["source_ids"].add(entry["id"])
            item["concepts"].add(concept_id)
    return [
        {
            "resource": resource,
            "source_ids": sorted(values["source_ids"]),
            "concepts": sorted(values["concepts"]),
        }
        for resource, values in sorted(external.items())
    ]


def _scan_text_window(
    window: str, relative: str, forbidden_paths: tuple[str, ...]
) -> None:
    if any(value and value in window for value in forbidden_paths):
        raise ADWikiError(f"included content contains a build-machine path: {relative}")
    if any(pattern.search(window) for pattern in SECRET_PATTERNS):
        raise ADWikiError(
            f"included content contains suspected secret material: {relative}"
        )


def _copy_scanned(
    source: Path,
    target: Path,
    relative: str,
    *,
    forbidden_paths: tuple[str, ...],
) -> tuple[str, int]:
    lower_name = source.name.lower()
    if lower_name in DENIED_NAMES or source.suffix.lower() in DENIED_SUFFIXES:
        raise ADWikiError(f"included path uses a denied sensitive filename: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    overlap = b""
    with source.open("rb") as reader, target.open("wb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(chunk)
            digest.update(chunk)
            size += len(chunk)
            window = overlap + chunk
            _scan_text_window(
                window.decode("utf-8", errors="ignore"),
                relative,
                forbidden_paths,
            )
            overlap = window[-512:]
    os.chmod(target, 0o644)
    return digest.hexdigest(), size


def _write_generated(path: Path, content: bytes, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.chmod(path, 0o755 if executable else 0o644)


def _payload_entries(candidate: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    manifest_path = candidate / "references/artifact-manifest.json"
    for path in sorted(candidate.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(candidate).as_posix()
        if path.is_symlink() or not path.is_file():
            raise ADWikiError(f"generated artifact contains an unsafe path: {relative}")
        if path == manifest_path:
            continue
        mode = path.stat().st_mode
        if relative == "SKILL.md":
            kind = "skill"
        elif relative.startswith("scripts/"):
            kind = "helper"
        elif relative.startswith("references/repository/"):
            kind = "knowledge"
        else:
            kind = "metadata"
        entries.append(
            {
                "executable": bool(mode & stat.S_IXUSR),
                "kind": kind,
                "path": relative,
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return entries


def _digest_entries(entries: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json_bytes(entries)).hexdigest()


def _git_revision(root: Path) -> str | None:
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root:
            return None
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if status_result.returncode != 0 or status_result.stdout:
            return None
        revision = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = revision.stdout.strip()
    return (
        value
        if revision.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value)
        else None
    )


def _tree_is_identical(left: Path, right: Path) -> bool:
    def inventory(root: Path) -> list[tuple[str, str, bool]]:
        values: list[tuple[str, str, bool]] = []
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                return []
            if path.is_file():
                values.append(
                    (
                        relative,
                        _sha256_file(path),
                        bool(path.stat().st_mode & stat.S_IXUSR),
                    )
                )
        return values

    return inventory(left) == inventory(right)


def _candidate_files(candidate: Path) -> list[Path]:
    files: list[tuple[str, Path]] = []
    for path in sorted(candidate.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(candidate).as_posix()
        if path.is_symlink() or not path.is_file():
            raise ADWikiError(f"generated artifact contains an unsafe path: {relative}")
        files.append((relative, path))
    return [path for _, path in sorted(files, key=lambda item: item[0])]


def _write_deterministic_zip(
    candidate: Path, archive_path: Path, skill_name: str
) -> None:
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
        strict_timestamps=True,
    ) as archive:
        archive.comment = b""
        for source in _candidate_files(candidate):
            relative = source.relative_to(candidate).as_posix()
            archive_name = f"{skill_name}/{relative}"
            source_stat = source.stat()
            mode = 0o755 if source_stat.st_mode & stat.S_IXUSR else 0o644
            info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.extra = b""
            info.comment = b""
            info.file_size = source_stat.st_size
            info._compresslevel = 9
            with source.open("rb") as reader, archive.open(
                info,
                mode="w",
                force_zip64=info.file_size >= 2**31,
            ) as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(chunk)
    os.chmod(archive_path, 0o644)


def _validate_deterministic_zip(
    candidate: Path,
    archive_path: Path,
    skill_name: str,
) -> dict[str, Any]:
    candidate_files = _candidate_files(candidate)
    expected_names = sorted(
        f"{skill_name}/{path.relative_to(candidate).as_posix()}"
        for path in candidate_files
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names != expected_names or len(names) != len(set(names)):
                raise ADWikiError(
                    "generated ZIP entry inventory does not match the Skill candidate"
                )
            if archive.comment:
                raise ADWikiError("generated ZIP archive comment must be empty")
            for source, info in zip(candidate_files, infos, strict=True):
                parts = info.filename.split("/")
                if (
                    info.filename.startswith("/")
                    or "\\" in info.filename
                    or any(not part or part in {".", ".."} for part in parts)
                    or parts[0] != skill_name
                    or info.is_dir()
                ):
                    raise ADWikiError(
                        f"generated ZIP contains an unsafe entry: {info.filename}"
                    )
                source_stat = source.stat()
                expected_mode = 0o755 if source_stat.st_mode & stat.S_IXUSR else 0o644
                archived_mode = info.external_attr >> 16
                if (
                    info.date_time != (1980, 1, 1, 0, 0, 0)
                    or info.create_system != 3
                    or info.compress_type != zipfile.ZIP_DEFLATED
                    or info.extra
                    or info.comment
                    or stat.S_IFMT(archived_mode) != stat.S_IFREG
                    or stat.S_IMODE(archived_mode) != expected_mode
                    or info.file_size != source_stat.st_size
                ):
                    raise ADWikiError(
                        f"generated ZIP entry metadata is invalid: {info.filename}"
                    )
                digest = hashlib.sha256()
                with archive.open(info) as reader:
                    for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != _sha256_file(source):
                    raise ADWikiError(
                        f"generated ZIP entry bytes differ from candidate: {info.filename}"
                    )
    except zipfile.BadZipFile as exc:
        raise ADWikiError("generated ZIP is invalid") from exc
    return {
        "sha256": _sha256_file(archive_path),
        "size": archive_path.stat().st_size,
    }


def _directory_target_status(candidate: Path, target: Path, skill_name: str) -> str:
    if target.is_symlink():
        raise ADWikiError("output target must not use a symlink")
    if not target.exists():
        return "created"
    if not target.is_dir() or not _tree_is_identical(candidate, target):
        raise ADWikiError(
            f"refusing to overwrite non-identical output target: {skill_name}"
        )
    return "unchanged"


def _archive_target_status(
    target: Path,
    skill_name: str,
    identity: dict[str, Any],
) -> str:
    if target.is_symlink():
        raise ADWikiError("output archive must not use a symlink")
    if not target.exists():
        return "created"
    if (
        not target.is_file()
        or target.stat().st_size != identity["size"]
        or _sha256_file(target) != identity["sha256"]
    ):
        raise ADWikiError(
            f"refusing to overwrite non-identical output archive: {skill_name}.zip"
        )
    return "unchanged"


def _rename_no_replace(source: Path, target: Path) -> None:
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    result: int
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise ADWikiError(
                "atomic no-replace publication is unavailable on this Linux host"
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, source_bytes, -100, target_bytes, 1)
    elif sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            raise ADWikiError(
                "atomic no-replace publication is unavailable on this macOS host"
            )
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(source_bytes, target_bytes, 0x00000004)
    elif os.name == "nt":
        try:
            os.rename(source, target)
        except FileExistsError as exc:
            raise ADWikiError(
                f"output target appeared during publication: {target.name}"
            ) from exc
        return
    else:
        raise ADWikiError("atomic no-replace publication is unavailable on this host")

    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ADWikiError(f"output target appeared during publication: {target.name}")
    raise OSError(error_number, os.strerror(error_number), str(target))


def _build_candidate(
    root: Path,
    candidate: Path,
    *,
    wiki_name: str,
    skill_name: str,
    config: dict[str, Any],
    bundle: Path,
    registry: dict[str, Any],
    source_files: list[Path],
    source_digests: dict[str, str],
    concepts: list[Path],
    external_sources: list[dict[str, Any]],
    warnings: list[str],
    git_revision: str | None,
    forbidden_paths: tuple[str, ...],
) -> dict[str, Any]:
    repository = candidate / "references/repository"
    raw_files = {record["path"] for record in registry["sources"]}
    bundle_entries: list[dict[str, Any]] = []
    for source in source_files:
        relative = source.relative_to(root).as_posix()
        digest, size = _copy_scanned(
            source,
            repository / relative,
            relative,
            forbidden_paths=forbidden_paths,
        )
        if digest != source_digests[relative]:
            raise ADWikiError(
                f"source changed while building delivery artifact: {relative}"
            )
        if _path_is_within(source, bundle):
            bundle_entries.append(
                {
                    "path": source.relative_to(bundle).as_posix(),
                    "sha256": digest,
                    "size": size,
                }
            )

    display_label = " ".join(
        part for part in re.split(r"[ _-]+", wiki_name.strip()) if part
    )
    if len(display_label) > 40:
        display_label = display_label[:39] + "…"
    skill_template = (TEMPLATE_ROOT / "SKILL.md.tmpl").read_text(encoding="utf-8")
    openai_template = (TEMPLATE_ROOT / "openai.yaml.tmpl").read_text(encoding="utf-8")
    skill_text = render_delivery_template(
        skill_template,
        {
            "BUNDLE_ROOT": str(config["bundle_root"]),
            "CONTENT_LANGUAGE": str(config["content_language"]),
            "DISPLAY_LABEL": display_label,
            "SKILL_NAME": skill_name,
        },
    )
    openai_text = render_delivery_template(
        openai_template,
        {"DISPLAY_LABEL": display_label, "SKILL_NAME": skill_name},
    )
    _write_generated(candidate / "SKILL.md", skill_text.encode("utf-8"))
    _write_generated(candidate / "agents/openai.yaml", openai_text.encode("utf-8"))
    _write_generated(
        candidate / "references/query-contract.md",
        (TEMPLATE_ROOT / "query-contract.md").read_bytes(),
    )
    _write_generated(
        candidate / "scripts/delivery_query.py",
        (PLUGIN_ROOT / "scripts/ad_wiki/delivery_query.py").read_bytes(),
        executable=False,
    )
    wrapper = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.dont_write_bytecode = True\n\n"
        "from delivery_query import main\n\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n"
    )
    _write_generated(
        candidate / "scripts/query_registered_raw.py",
        wrapper.encode("utf-8"),
        executable=True,
    )

    payload = _payload_entries(candidate)
    artifact_digest = _digest_entries(payload)
    bundle_digest = _digest_entries(bundle_entries)
    registry_bytes = (root / ".ad-wiki/source-registry.json").read_bytes()
    capabilities = {
        "compiled_query": True,
        "deployment": False,
        "helper_raw_fallback": True,
        "maintenance": False,
        "manual_raw_fallback": True,
        "writeback": False,
    }
    counts = {
        "concepts": len(concepts),
        "external_sources": len(external_sources),
        "files": len(payload) + 1,
        "raw_files": len(raw_files),
        "registered_sources": len(registry["sources"]),
    }
    manifest = {
        "artifact_digest": artifact_digest,
        "built_with": {
            "delivery_template_version": DELIVERY_TEMPLATE_VERSION,
            "okf_version": OKF_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "profile_version": PROFILE_VERSION,
        },
        "capabilities": capabilities,
        "counts": counts,
        "excluded": EXCLUDED_PATHS,
        "external_sources": external_sources,
        "payload": payload,
        "schema_version": "1",
        "skill_name": skill_name,
        "source": {
            "bundle_digest": bundle_digest,
            "bundle_root": str(config["bundle_root"]),
            "git_revision": git_revision,
            "raw_root": str(config["raw_root"]),
            "source_registry_digest": hashlib.sha256(registry_bytes).hexdigest(),
        },
        "warnings": warnings,
        "wiki_name": wiki_name,
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    _write_generated(candidate / "references/artifact-manifest.json", manifest_bytes)
    return {
        "artifact_digest": artifact_digest,
        "capabilities": capabilities,
        "counts": counts,
        "excluded": EXCLUDED_PATHS,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "warnings": warnings,
    }


def build_wiki_skill(
    repo: str | Path,
    *,
    output_parent: str | Path,
    wiki_name: str | None = None,
    output_format: str = "directory",
) -> dict[str, Any]:
    if output_format not in OUTPUT_FORMATS:
        raise ADWikiError(
            "output format must be one of: " + ", ".join(sorted(OUTPUT_FORMATS))
        )
    unresolved_root = Path(repo).expanduser()
    if unresolved_root.is_symlink():
        raise ADWikiError("AD Wiki repository root must not use a symlink")
    root = unresolved_root.resolve()
    source_paths = tuple(dict.fromkeys((str(unresolved_root.absolute()), str(root))))
    if not root.is_dir():
        raise ADWikiError("AD Wiki repository must be an existing directory")
    selected_name = wiki_name if wiki_name is not None else root.name
    name_source = "explicit" if wiki_name is not None else "repository-basename"
    skill_name = canonical_skill_name(selected_name)

    unresolved_output = Path(output_parent).expanduser()
    if unresolved_output.exists() and unresolved_output.is_symlink():
        raise ADWikiError("output parent must not use a symlink")
    output_root = unresolved_output.resolve()
    directory_target = output_root / skill_name
    archive_target = output_root / f"{skill_name}.zip"
    requested_targets: list[Path] = []
    if output_format in {"directory", "both"}:
        requested_targets.append(directory_target)
    if output_format in {"zip", "both"}:
        requested_targets.append(archive_target)
    if any(_path_is_within(target, root) for target in requested_targets):
        raise ADWikiError("output target must be outside the source Wiki repository")

    raw_root, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    config = dict(config)
    config["bundle_root"] = _safe_configured_root(
        config.get("bundle_root", "wiki"), "bundle_root"
    )
    config["raw_root"] = _safe_configured_root(
        config.get("raw_root", "raw"), "raw_root"
    )
    config["content_language"] = config.get("content_language", "zh-CN")
    for relative, expected in STATIC_AGENT_FILES.items():
        path = root / relative
        if relative == "CLAUDE.md" and not path.exists():
            continue
        if (
            not path.is_file()
            or path.is_symlink()
            or path.read_text(encoding="utf-8") != expected
        ):
            raise ADWikiError(
                f"static Query entry is missing or differs from the canonical contract: {relative}"
            )
    validation = validate_repository(root)
    if not validation["ok"]:
        codes = ", ".join(sorted({item["code"] for item in validation["errors"]}))
        raise ADWikiError(f"AD Wiki validation failed: {codes}")
    blocking_warnings = [
        item
        for item in validation["warnings"]
        if item["code"] not in REVIEWABLE_WARNING_CODES
    ]
    if blocking_warnings:
        codes = ", ".join(sorted({item["code"] for item in blocking_warnings}))
        raise ADWikiError(f"AD Wiki deployability validation failed: {codes}")
    raw_report = guard_raw(root)
    if not raw_report["ok"]:
        codes = ", ".join(sorted({item["code"] for item in raw_report["violations"]}))
        raise ADWikiError(f"registered Raw validation failed: {codes}")

    registry = _load_registry(root)
    bundle_files = _bundle_files(root, bundle)
    concepts = _concept_inventory(bundle)
    required = [
        root / "ad-wiki.yaml",
        root / "AGENTS.md",
        root / ".ad-wiki/source-registry.json",
    ]
    optional = [root / "CLAUDE.md", root / ".ad-wiki/domain.md"]
    raw_files = [root / record["path"] for record in registry["sources"]]
    source_files = [
        *required,
        *(path for path in optional if path.exists()),
        *bundle_files,
        *raw_files,
    ]
    unique_files: dict[str, Path] = {}
    for path in source_files:
        relative = path.relative_to(root).as_posix()
        _safe_regular_file(root, path, relative)
        if path in raw_files and not _path_is_within(path.resolve(), raw_root):
            raise ADWikiError(f"registered Raw source is outside raw_root: {relative}")
        unique_files[relative] = path
    source_files = [unique_files[key] for key in sorted(unique_files)]
    if len(source_files) > MAX_INCLUDED_FILES:
        raise ADWikiError(f"delivery includes more than {MAX_INCLUDED_FILES} files")
    source_digests = {
        path.relative_to(root).as_posix(): _sha256_file(path) for path in source_files
    }
    external_sources = _external_sources(root, bundle, concepts, registry["sources"])
    warnings = sorted(
        {f"{item['code']}:{item['path']}" for item in validation["warnings"]}
        | (
            {f"external-primary-sources:{len(external_sources)}"}
            if external_sources
            else set()
        )
    )
    git_revision = _git_revision(root)
    if git_revision is None:
        warnings.append("git-revision-unavailable")
        warnings.sort()

    output_root.mkdir(parents=True, exist_ok=True)
    temp_path = Path(tempfile.mkdtemp(prefix=f".{skill_name}.", dir=output_root))
    os.chmod(temp_path, 0o700)
    temp_archive: Path | None = None
    try:
        result = _build_candidate(
            root,
            temp_path,
            wiki_name=selected_name,
            skill_name=skill_name,
            config=config,
            bundle=bundle,
            registry=registry,
            source_files=source_files,
            source_digests=source_digests,
            concepts=concepts,
            external_sources=external_sources,
            warnings=warnings,
            git_revision=git_revision,
            forbidden_paths=source_paths,
        )
        archive_identity: dict[str, Any] | None = None
        if output_format in {"zip", "both"}:
            descriptor, temp_archive_name = tempfile.mkstemp(
                prefix=f".{skill_name}.",
                suffix=".zip",
                dir=output_root,
            )
            os.close(descriptor)
            temp_archive = Path(temp_archive_name)
            _write_deterministic_zip(temp_path, temp_archive, skill_name)
            archive_identity = _validate_deterministic_zip(
                temp_path,
                temp_archive,
                skill_name,
            )
        for relative, expected in source_digests.items():
            if _sha256_file(root / relative) != expected:
                raise ADWikiError(
                    f"source changed before delivery publication: {relative}"
                )

        directory_status: str | None = None
        archive_status: str | None = None
        if output_format in {"directory", "both"}:
            directory_status = _directory_target_status(
                temp_path,
                directory_target,
                skill_name,
            )
        if output_format in {"zip", "both"}:
            if temp_archive is None or archive_identity is None:
                raise ADWikiError("ZIP candidate identity is unavailable")
            archive_status = _archive_target_status(
                archive_target,
                skill_name,
                archive_identity,
            )

        archive_published = False
        published_archive_stat: tuple[int, int] | None = None
        try:
            if archive_status == "created":
                if temp_archive is None:
                    raise ADWikiError("ZIP candidate is unavailable")
                archive_stat = temp_archive.stat(follow_symlinks=False)
                published_archive_stat = (archive_stat.st_dev, archive_stat.st_ino)
                _rename_no_replace(temp_archive, archive_target)
                archive_published = True
                current_archive_stat = archive_target.stat(follow_symlinks=False)
                if (
                    current_archive_stat.st_dev,
                    current_archive_stat.st_ino,
                ) != published_archive_stat:
                    raise ADWikiError(
                        "ZIP publication ownership changed before it could be verified"
                    )
            if directory_status == "created":
                directory_stat = temp_path.stat(follow_symlinks=False)
                published_directory_stat = (
                    directory_stat.st_dev,
                    directory_stat.st_ino,
                )
                _rename_no_replace(temp_path, directory_target)
                current_directory_stat = directory_target.stat(follow_symlinks=False)
                if (
                    current_directory_stat.st_dev,
                    current_directory_stat.st_ino,
                ) != published_directory_stat:
                    raise ADWikiError(
                        "directory publication ownership changed before it could be verified"
                    )
        except Exception as publish_error:
            if archive_published:
                try:
                    current_stat = archive_target.stat(follow_symlinks=False)
                    current_identity = (current_stat.st_dev, current_stat.st_ino)
                    if (
                        published_archive_stat is None
                        or current_identity != published_archive_stat
                        or archive_identity is None
                        or not stat.S_ISREG(current_stat.st_mode)
                        or current_stat.st_size != archive_identity["size"]
                        or _sha256_file(archive_target) != archive_identity["sha256"]
                    ):
                        raise ADWikiError(
                            "delivery publication failed and ZIP rollback ownership changed; "
                            "the replacement archive was preserved"
                        )
                    archive_target.unlink()
                except ADWikiError:
                    raise
                except OSError as rollback_error:
                    raise ADWikiError(
                        "delivery publication failed and the current-run ZIP rollback also failed: "
                        f"{rollback_error}"
                    ) from publish_error
            raise

        requested_statuses = [
            status
            for status in (directory_status, archive_status)
            if status is not None
        ]
        status_value = "created" if "created" in requested_statuses else "unchanged"
        directory_result = (
            {"path": str(directory_target), "status": directory_status}
            if directory_status is not None
            else None
        )
        archive_result = (
            {
                "path": str(archive_target),
                "sha256": archive_identity["sha256"],
                "size": archive_identity["size"],
                "status": archive_status,
            }
            if archive_status is not None and archive_identity is not None
            else None
        )
        primary_output = (
            directory_target
            if output_format in {"directory", "both"}
            else archive_target
        )
        return {
            **result,
            "archive": archive_result,
            "directory": directory_result,
            "format": output_format,
            "name_source": name_source,
            "output": str(primary_output),
            "skill_name": skill_name,
            "status": status_value,
            "wiki_name": selected_name,
        }
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)
        if temp_archive is not None and temp_archive.exists():
            temp_archive.unlink()
