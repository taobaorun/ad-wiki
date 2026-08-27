from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .core import (
    ADWikiError,
    ALLOWED_OPERATIONS,
    ALLOWED_RISKS,
    ALLOWED_STATES,
    _atomic_write_json,
    _atomic_write_text,
    _configured_roots,
    _load_registry,
    _path_is_within,
    _repository_root,
    _require_supported_profile,
    _resolve_inside,
    _utc_now,
)
from .locking import repository_lock


CODE_SOURCE_REGISTRY_VERSION = 1
WORKTREE_BINDINGS_VERSION = 1
SAFE_REMOTE_SCHEMES = frozenset({"git", "http", "https", "ssh"})
SHA1 = re.compile(r"[0-9a-f]{40}")
REPOSITORY_KEY = re.compile(r"[0-9a-f]{16}")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SAFE_REPOSITORY_NAME = re.compile(r"[^\x00-\x1f/\\]{1,255}")


def _git(code_root: Path, *args: str, allow_failure: bool = False) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=code_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ADWikiError(f"cannot inspect Git code repository: {exc}") from exc
    if result.returncode != 0:
        if allow_failure:
            return None
        detail = (result.stderr or result.stdout).strip()
        raise ADWikiError(f"cannot inspect Git code repository: {detail or 'git command failed'}")
    return result.stdout.strip()


def normalize_remote(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    remote = value.strip().rstrip("/")
    scp = re.fullmatch(r"([^/@:]+@[^/:]+):(.+)", remote)
    if scp:
        remote = f"ssh://{scp.group(1)}/{scp.group(2)}"
    if Path(remote).is_absolute() or remote.startswith(("./", "../")):
        return None
    try:
        parsed = urlsplit(remote)
        password = parsed.password
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() not in SAFE_REMOTE_SCHEMES
        or not parsed.hostname
        or password is not None
        or (parsed.scheme.casefold() in {"http", "https"} and parsed.username is not None)
        or parsed.query
        or parsed.fragment
    ):
        return None
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path or path == "/":
        return None
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc, path, "", ""))


def repository_key(code_source: dict[str, Any]) -> str:
    remote = code_source.get("remote")
    if remote:
        identity = f"remote:{remote}"
    else:
        roots = ",".join(sorted(code_source.get("root_commits", [])))
        identity = f"local:{code_source.get('repository', 'code')}:{roots}"
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


_repository_key = repository_key


def _safe_repository_name(value: Any, remote: str | None) -> str:
    if remote is not None:
        candidate = Path(urlsplit(remote).path).name
        if candidate and candidate not in {".", ".."} and SAFE_REPOSITORY_NAME.fullmatch(candidate):
            return candidate
    if (
        isinstance(value, str)
        and value not in {".", ".."}
        and Path(value).name == value
        and SAFE_REPOSITORY_NAME.fullmatch(value)
    ):
        return value
    raise ADWikiError("code source repository name is unsafe or non-portable")


def inspect_code_repository(
    code_repo: str | Path,
    *,
    require_clean: bool = True,
) -> dict[str, Any]:
    unresolved = Path(code_repo).expanduser()
    if unresolved.is_symlink():
        raise ADWikiError("code repository root must not use a symlink")
    root = unresolved.resolve()
    if not root.is_dir():
        raise ADWikiError("code repository must be an existing Git worktree")
    top_level = _git(root, "rev-parse", "--show-toplevel", allow_failure=True)
    if top_level is None:
        raise ADWikiError("code repository must be a Git worktree")
    if Path(top_level).resolve() != root:
        raise ADWikiError("code repository path must be the Git worktree root")
    revision = _git(root, "rev-parse", "--verify", "HEAD^{commit}", allow_failure=True)
    if revision is None or not SHA1.fullmatch(revision):
        raise ADWikiError("code repository requires a committed HEAD")
    status = _git(root, "status", "--porcelain", "--untracked-files=all") or ""
    if require_clean and status:
        raise ADWikiError("code repository must be a clean Git worktree")
    remote = normalize_remote(_git(root, "remote", "get-url", "origin", allow_failure=True))
    root_commits_text = _git(root, "rev-list", "--max-parents=0", "HEAD") or ""
    return {
        "remote": remote,
        "repository": root.name,
        "revision": revision,
        "root_commits": sorted(line for line in root_commits_text.splitlines() if line),
        "worktree_clean": not bool(status),
    }


def _empty_registry() -> dict[str, Any]:
    return {"sources": [], "version": CODE_SOURCE_REGISTRY_VERSION}


def _resolve_lexical_inside(root: Path, relative: str | Path, label: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise ADWikiError(f"{label} must be repository-relative")
    lexical = root
    for part in value.parts:
        lexical = lexical / part
        if lexical.is_symlink():
            raise ADWikiError(f"{label} path must not use a symlink")
    if not _path_is_within(lexical.resolve(), root):
        raise ADWikiError(f"{label} resolves outside repository")
    return lexical


def _registry_path(root: Path) -> Path:
    return _resolve_lexical_inside(
        root, ".ad-wiki/code-source-registry.json", "code source registry"
    )


def _require_initialized_wiki(root: Path) -> None:
    raw, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    if not raw.is_dir() or not bundle.is_dir():
        raise ADWikiError("code source operation requires an initialized AD Wiki")
    _load_registry(root)


def _validate_source_record(root: Path, record: Any, index: int) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != {
        "canonical_remote",
        "repository",
        "repository_key",
        "root_commits",
        "snapshots",
    }:
        raise ADWikiError(f"malformed code source registry record at index {index}")
    key = record["repository_key"]
    remote = record["canonical_remote"]
    repository = record["repository"]
    roots = record["root_commits"]
    snapshots = record["snapshots"]
    if not isinstance(key, str) or not REPOSITORY_KEY.fullmatch(key):
        raise ADWikiError(f"malformed code source registry record at index {index}")
    if remote is not None and (
        not isinstance(remote, str) or normalize_remote(remote) != remote
    ):
        raise ADWikiError(f"malformed code source registry record at index {index}")
    if (
        not isinstance(repository, str)
        or repository in {".", ".."}
        or Path(repository).name != repository
        or not SAFE_REPOSITORY_NAME.fullmatch(repository)
    ):
        raise ADWikiError(f"malformed code source registry record at index {index}")
    if (
        not isinstance(roots, list)
        or not roots
        or not all(isinstance(item, str) and SHA1.fullmatch(item) for item in roots)
        or roots != sorted(set(roots))
        or not isinstance(snapshots, list)
    ):
        raise ADWikiError(f"malformed code source registry record at index {index}")
    expected_key = repository_key(
        {"remote": remote, "repository": repository, "root_commits": roots}
    )
    if expected_key != key:
        raise ADWikiError(f"code source registry key mismatch at index {index}")
    normalized_snapshots: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    _, bundle, _ = _configured_roots(root)
    for snapshot_index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "revision",
            "source_summary_path",
            "validated_run_id",
        }:
            raise ADWikiError(
                f"malformed code source snapshot at record {index}, index {snapshot_index}"
            )
        revision = snapshot["revision"]
        summary = snapshot["source_summary_path"]
        run_id = snapshot["validated_run_id"]
        if (
            not isinstance(revision, str)
            or not SHA1.fullmatch(revision)
            or not isinstance(summary, str)
            or not isinstance(run_id, str)
            or not RUN_ID.fullmatch(run_id)
        ):
            raise ADWikiError(
                f"malformed code source snapshot at record {index}, index {snapshot_index}"
            )
        summary_path = _resolve_lexical_inside(root, summary, "code source summary")
        run_path = _resolve_lexical_inside(
            root,
            f".ad-wiki/runs/{run_id}/run.json",
            "validated Code Wiki run",
        )
        if (
            Path(summary).is_absolute()
            or not _path_is_within(summary_path, bundle)
            or summary_path.suffix.lower() != ".md"
            or summary_path.is_symlink()
            or not summary_path.is_file()
            or run_path.is_symlink()
            or not run_path.is_file()
        ):
            raise ADWikiError(
                f"malformed code source snapshot at record {index}, index {snapshot_index}"
            )
        identity = (revision, summary, run_id)
        if identity in seen:
            raise ADWikiError(f"duplicate code source snapshot at record {index}")
        seen.add(identity)
        normalized_snapshots.append(dict(snapshot))
    return {
        "canonical_remote": remote,
        "repository": repository,
        "repository_key": key,
        "root_commits": roots,
        "snapshots": sorted(
            normalized_snapshots,
            key=lambda item: (
                item["revision"],
                item["source_summary_path"],
                item["validated_run_id"],
            ),
        ),
    }


def load_code_source_registry(repo: str | Path) -> dict[str, Any]:
    root = _repository_root(repo)
    path = _registry_path(root)
    if path.is_symlink():
        raise ADWikiError("code source registry must not use a symlink")
    if not path.exists():
        return _empty_registry()
    if not path.is_file():
        raise ADWikiError("code source registry must be a regular file")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ADWikiError(f"invalid code source registry: {exc}") from exc
    return _normalize_registry_value(root, registry)


def _normalize_registry_value(root: Path, registry: Any) -> dict[str, Any]:
    if (
        not isinstance(registry, dict)
        or set(registry) != {"sources", "version"}
        or type(registry.get("version")) is not int
        or registry.get("version") != CODE_SOURCE_REGISTRY_VERSION
        or not isinstance(registry.get("sources"), list)
    ):
        raise ADWikiError("unsupported code source registry format")
    sources = [
        _validate_source_record(root, record, index)
        for index, record in enumerate(registry["sources"])
    ]
    keys = [record["repository_key"] for record in sources]
    if len(keys) != len(set(keys)):
        raise ADWikiError("duplicate code source repository identity")
    return {
        "sources": sorted(sources, key=lambda item: item["repository_key"]),
        "version": 1,
    }


def _merge_validated_run(
    root: Path,
    registry: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    code_wiki = report.get("code_wiki")
    if report.get("operation") != "code-wiki" or not isinstance(code_wiki, dict):
        raise ADWikiError("portable code source registration requires a Code Wiki run")
    source = code_wiki.get("code_source")
    summary = code_wiki.get("source_summary_path")
    run_id = report.get("run_id")
    if (
        not isinstance(source, dict)
        or not isinstance(summary, str)
        or not isinstance(run_id, str)
        or not RUN_ID.fullmatch(run_id)
    ):
        raise ADWikiError("Code Wiki run is missing code source provenance")
    remote_value = source.get("remote")
    repository_value = source.get("repository")
    revision_value = source.get("revision")
    roots_value = source.get("root_commits")
    if (
        (remote_value is not None and not isinstance(remote_value, str))
        or not isinstance(repository_value, str)
        or not isinstance(revision_value, str)
        or not SHA1.fullmatch(revision_value)
        or not isinstance(roots_value, list)
        or not roots_value
        or not all(isinstance(item, str) and SHA1.fullmatch(item) for item in roots_value)
    ):
        raise ADWikiError("Code Wiki run has malformed code source provenance")
    summary_path = _resolve_lexical_inside(root, summary, "code source summary")
    _, bundle, _ = _configured_roots(root)
    if not summary_path.is_file() or not _path_is_within(summary_path, bundle):
        raise ADWikiError("Code Wiki source summary is missing or outside the Bundle")
    normalized_source = {
        **source,
        "remote": normalize_remote(remote_value),
        "root_commits": sorted(set(roots_value)),
    }
    normalized_source["repository"] = _safe_repository_name(
        repository_value, normalized_source["remote"]
    )
    key = repository_key(normalized_source)
    snapshot = {
        "revision": revision_value,
        "source_summary_path": summary,
        "validated_run_id": run_id,
    }
    records = {item["repository_key"]: dict(item) for item in registry["sources"]}
    record = records.get(key)
    identity = {
        "canonical_remote": normalized_source.get("remote"),
        "repository": normalized_source["repository"],
        "repository_key": key,
        "root_commits": normalized_source["root_commits"],
    }
    if record is None:
        record = {**identity, "snapshots": []}
    elif any(record[field] != value for field, value in identity.items()):
        raise ADWikiError("Code Wiki source conflicts with portable registry identity")
    snapshots = {
        (item["revision"], item["source_summary_path"], item["validated_run_id"]): item
        for item in record["snapshots"]
    }
    snapshots[(snapshot["revision"], snapshot["source_summary_path"], snapshot["validated_run_id"])] = snapshot
    record["snapshots"] = sorted(
        snapshots.values(),
        key=lambda item: (item["revision"], item["source_summary_path"], item["validated_run_id"]),
    )
    records[key] = record
    return {"sources": [records[item] for item in sorted(records)], "version": 1}


def register_validated_code_source(repo: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    root = _repository_root(repo)
    registry = _normalize_registry_value(
        root,
        _merge_validated_run(root, load_code_source_registry(root), report),
    )
    _atomic_write_json(_registry_path(root), registry)
    return registry


def rebuild_code_source_registry(repo: str | Path) -> dict[str, Any]:
    root = _repository_root(repo)
    _require_initialized_wiki(root)
    with repository_lock(root, "rebuild-code-source-registry"):
        runs_root = _resolve_lexical_inside(root, ".ad-wiki/runs", "run root")
        registry = _empty_registry()
        used_runs: list[str] = []
        if runs_root.exists():
            for path in sorted(runs_root.iterdir(), key=lambda item: item.name):
                run_path = path / "run.json"
                if path.is_symlink() or run_path.is_symlink():
                    raise ADWikiError("historical run path must not use a symlink")
                if not path.is_dir() or not run_path.exists():
                    continue
                if not run_path.is_file():
                    raise ADWikiError("historical run report must be a regular file")
                try:
                    report = json.loads(run_path.read_text(encoding="utf-8"))
                except OSError as exc:
                    raise ADWikiError(
                        f"cannot read historical run report: {path.name}"
                    ) from exc
                except json.JSONDecodeError as exc:
                    raise ADWikiError(
                        f"invalid historical run report: {path.name}"
                    ) from exc
                if (
                    not isinstance(report, dict)
                    or report.get("run_id") != path.name
                    or report.get("operation") not in ALLOWED_OPERATIONS
                    or report.get("status") not in ALLOWED_STATES
                    or report.get("risk") not in ALLOWED_RISKS - {"prohibited"}
                    or not isinstance(report.get("inputs"), list)
                    or not isinstance(report.get("read_set"), list)
                    or not isinstance(report.get("write_set"), list)
                    or not isinstance(report.get("validations"), list)
                ):
                    raise ADWikiError(
                        f"malformed historical run report: {path.name}"
                    )
                events = report.get("events", []) if isinstance(report, dict) else []
                reached_validated = isinstance(events, list) and any(
                    isinstance(event, dict) and event.get("state") == "VALIDATED"
                    for event in events
                )
                if (
                    isinstance(report, dict)
                    and report.get("operation") == "code-wiki"
                    and (
                        report.get("status") in {"COMMITTED", "REVIEWED", "VALIDATED"}
                        or reached_validated
                    )
                ):
                    registry = _merge_validated_run(root, registry, report)
                    used_runs.append(str(report["run_id"]))
        registry = _normalize_registry_value(root, registry)
        _atomic_write_json(_registry_path(root), registry)
        return {"registry": registry, "run_ids": sorted(used_runs), "status": "rebuilt"}


def _binding_root(root: Path) -> Path:
    relative = Path(".ad-wiki/cache/code-worktrees")
    lexical = root
    for part in relative.parts:
        lexical = lexical / part
        if lexical.is_symlink():
            raise ADWikiError("code worktree cache path must not use a symlink")
    return _resolve_inside(root, relative, "code worktree cache")


def _load_bindings(root: Path) -> dict[str, Any]:
    path = _binding_root(root) / "bindings.json"
    if path.is_symlink():
        raise ADWikiError("code worktree bindings must not use a symlink")
    if not path.exists():
        return {"bindings": [], "version": WORKTREE_BINDINGS_VERSION}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ADWikiError(f"invalid code worktree bindings: {exc}") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"bindings", "version"}
        or type(value.get("version")) is not int
        or value.get("version") != WORKTREE_BINDINGS_VERSION
        or not isinstance(value.get("bindings"), list)
    ):
        raise ADWikiError("unsupported code worktree binding format")
    normalized: list[dict[str, Any]] = []
    for index, binding in enumerate(value["bindings"]):
        if not isinstance(binding, dict) or set(binding) != {
            "bound_at",
            "canonical_remote",
            "path",
            "repository",
            "repository_key",
            "root_commits",
        }:
            raise ADWikiError(f"malformed code worktree binding at index {index}")
        path_value = binding["path"]
        if (
            not isinstance(path_value, str)
            or not Path(path_value).is_absolute()
            or not isinstance(binding["repository_key"], str)
            or not REPOSITORY_KEY.fullmatch(binding["repository_key"])
            or not isinstance(binding["repository"], str)
            or binding["repository"] in {".", ".."}
            or Path(binding["repository"]).name != binding["repository"]
            or not SAFE_REPOSITORY_NAME.fullmatch(binding["repository"])
            or (
                binding["canonical_remote"] is not None
                and normalize_remote(binding["canonical_remote"]) != binding["canonical_remote"]
            )
            or not isinstance(binding["root_commits"], list)
            or not all(isinstance(item, str) and SHA1.fullmatch(item) for item in binding["root_commits"])
            or binding["root_commits"] != sorted(set(binding["root_commits"]))
            or not isinstance(binding["bound_at"], str)
        ):
            raise ADWikiError(f"malformed code worktree binding at index {index}")
        if repository_key(
            {
                "remote": binding["canonical_remote"],
                "repository": binding["repository"],
                "root_commits": binding["root_commits"],
            }
        ) != binding["repository_key"]:
            raise ADWikiError(f"code worktree binding key mismatch at index {index}")
        normalized.append(dict(binding))
    return {
        "bindings": sorted(normalized, key=lambda item: (item["repository_key"], item["path"])),
        "version": WORKTREE_BINDINGS_VERSION,
    }


def _write_private_bindings(root: Path, value: dict[str, Any]) -> None:
    target = _binding_root(root)
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(target, 0o700)
    except OSError:
        pass
    ignore = target / ".gitignore"
    if ignore.is_symlink() or (ignore.exists() and not ignore.is_file()):
        raise ADWikiError("code worktree cache gitignore must be a regular file")
    if ignore.exists() and ignore.read_text(encoding="utf-8") != "*\n":
        raise ADWikiError("code worktree cache gitignore contract changed")
    if not ignore.exists():
        _atomic_write_text(ignore, "*\n")
    path = target / "bindings.json"
    descriptor, temp_name = tempfile.mkstemp(dir=target, prefix=".bindings.", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def bind_code_worktree(repo: str | Path, *, code_repo: str | Path) -> dict[str, Any]:
    root = _repository_root(repo)
    _require_initialized_wiki(root)
    with repository_lock(root, "bind-code-worktree"):
        source = inspect_code_repository(code_repo, require_clean=False)
        path = str(Path(code_repo).expanduser().resolve())
        binding = {
            "bound_at": _utc_now(),
            "canonical_remote": source["remote"],
            "path": path,
            "repository": source["repository"],
            "repository_key": repository_key(source),
            "root_commits": source["root_commits"],
        }
        value = _load_bindings(root)
        bindings = {
            (item["repository_key"], item["path"]): item for item in value["bindings"]
        }
        bindings[(binding["repository_key"], path)] = binding
        value["bindings"] = [bindings[key] for key in sorted(bindings)]
        _write_private_bindings(root, value)
        return {"binding": binding, "code_source": source, "status": "bound"}


def resolve_code_worktree(
    repo: str | Path,
    *,
    canonical_remote: str | None = None,
    repository_key: str | None = None,
    revision: str | None = None,
    require_clean: bool = False,
) -> dict[str, Any]:
    root = _repository_root(repo)
    _require_initialized_wiki(root)
    if (canonical_remote is None) == (repository_key is None):
        raise ADWikiError("provide exactly one of canonical_remote or repository_key")
    if revision is not None and not SHA1.fullmatch(revision):
        raise ADWikiError("requested code revision must be a full commit SHA")
    if canonical_remote is not None:
        normalized_remote = normalize_remote(canonical_remote)
        if normalized_remote is None:
            raise ADWikiError("canonical remote is unsafe or non-portable")
        target_key = _repository_key({"remote": normalized_remote})
    else:
        if repository_key is None or not REPOSITORY_KEY.fullmatch(repository_key):
            raise ADWikiError("repository identity must be a 16-character hex key")
        normalized_remote = None
        target_key = repository_key
    candidates = [
        item for item in _load_bindings(root)["bindings"] if item["repository_key"] == target_key
    ]
    valid: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for item in candidates:
        try:
            source = inspect_code_repository(item["path"], require_clean=False)
            if normalized_remote is not None and source["remote"] != normalized_remote:
                raise ADWikiError("canonical remote changed")
            if source["repository"] != item["repository"]:
                raise ADWikiError("repository name changed")
            if sorted(source["root_commits"]) != sorted(item["root_commits"]):
                raise ADWikiError("repository root identity changed")
            if _repository_key(source) != target_key:
                raise ADWikiError("repository identity changed")
            if require_clean and not source["worktree_clean"]:
                raise ADWikiError("worktree is dirty")
            if revision is not None:
                code_root = Path(item["path"])
                if _git(code_root, "cat-file", "-e", f"{revision}^{{commit}}", allow_failure=True) is None:
                    raise ADWikiError("requested revision is unavailable")
            valid.append(
                {
                    "code_source": source,
                    "path": item["path"],
                    "read_mode": "git-object" if revision is not None else "working-tree",
                    "read_revision": revision or source["revision"],
                }
            )
        except ADWikiError as exc:
            diagnostics.append(f"{item['path']}: {exc}")
    if len(valid) == 1:
        return {"diagnostics": diagnostics, "resolution": valid[0], "status": "resolved"}
    if len(valid) > 1:
        return {"candidates": valid, "diagnostics": diagnostics, "status": "ambiguous"}
    return {"diagnostics": diagnostics, "status": "missing"}
