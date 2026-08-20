from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .core import (
    ADWikiError,
    ALLOWED_OPERATIONS,
    ALLOWED_RISKS,
    HUMAN_ACTOR,
    PLUGIN_VERSION,
    PROFILE_VERSION,
    RUN_ID,
    STATE_TRANSITIONS,
    _atomic_write_json,
    _atomic_write_text,
    _bundle_markdown_files,
    _configured_roots,
    _content_language,
    _frontmatter,
    _load_config,
    _load_registry,
    _path_is_within,
    _relative_posix,
    _repository_root,
    _require_supported_profile,
    _resolve_inside,
    _sha256_file,
    _source_entries,
    _top_level,
    _utc_now,
    _validate_run_paths,
    build_indexes,
    guard_raw,
    validate_repository,
)


WRITABLE_OPERATIONS = {"ingest", "writeback", "lint", "migrate"}
SEARCH_SEGMENT = re.compile(r"[a-z0-9][a-z0-9_-]*|[\u3400-\u9fff]+", re.IGNORECASE)
QUERY_NOISE = (
    "告诉我",
    "有什么",
    "什么是",
    "的",
    "是什么",
    "为什么",
    "什么",
    "有何",
    "如何",
    "怎么",
    "怎样",
    "请问",
    "一下",
    "查询",
    "介绍",
    "讲讲",
    "相关",
    "问题",
)
QUERY_TOKEN_NOISE = frozenset(
    {
        "a",
        "about",
        "an",
        "are",
        "can",
        "describe",
        "explain",
        "how",
        "is",
        "me",
        "please",
        "s",
        "tell",
        "the",
        "was",
        "were",
        "what",
        "why",
        "you",
    }
)
CONCEPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*")


def _run_path(root: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id) or ".." in run_id:
        raise ADWikiError(f"invalid run id: {run_id}")
    runs_root = root / ".ad-wiki/runs"
    if runs_root.is_symlink():
        raise ADWikiError(".ad-wiki/runs must not be a symlink")
    resolved_runs = _resolve_inside(root, runs_root, "run root")
    run_directory = resolved_runs / run_id
    if run_directory.is_symlink() or not _path_is_within(run_directory.resolve(), root):
        raise ADWikiError("run directory must not escape the repository or use a symlink")
    return run_directory / "run.json"


def _load_run(root: Path, run_id: str) -> dict[str, Any]:
    path = _run_path(root, run_id)
    if not path.is_file():
        raise ADWikiError(f"run not found: {run_id}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ADWikiError(f"invalid run report: {exc}") from exc
    if not isinstance(report, dict) or report.get("run_id") != run_id:
        raise ADWikiError(f"invalid run report identity: {run_id}")
    return report


def _save_run(root: Path, report: dict[str, Any]) -> None:
    report["updated_at"] = _utc_now()
    _atomic_write_json(_run_path(root, str(report["run_id"])), report)


def _advance(report: dict[str, Any], state: str, **event: Any) -> None:
    previous = str(report.get("status", ""))
    if state != previous and state not in STATE_TRANSITIONS.get(previous, set()):
        raise ADWikiError(f"invalid state transition: {previous} -> {state}")
    report["status"] = state
    if state != previous:
        report.setdefault("events", []).append({"at": _utc_now(), "state": state, **event})


def _digest_or_none(path: Path, root: Path) -> str | None:
    if path.is_symlink():
        raise ADWikiError(f"baseline path must not be a symlink: {_relative_posix(path, root)}")
    if not path.exists():
        return None
    if not path.is_file():
        raise ADWikiError(f"baseline path must be a regular file: {_relative_posix(path, root)}")
    return _sha256_file(path)


def _baseline(root: Path, paths: Iterable[str]) -> dict[str, str | None]:
    return {
        relative: _digest_or_none(_resolve_inside(root, relative, "baseline path"), root)
        for relative in sorted(set(paths))
    }


def _check_baseline(root: Path, baseline: dict[str, str | None]) -> None:
    drifted: list[str] = []
    for relative, expected in baseline.items():
        actual = _digest_or_none(_resolve_inside(root, relative, "baseline path"), root)
        if actual != expected:
            drifted.append(relative)
    if drifted:
        raise ADWikiError("repository baseline drifted after planning: " + ", ".join(drifted))


def _registered_source_hashes(root: Path, inputs: list[str], operation: str) -> dict[str, str]:
    registry = _load_registry(root)
    by_path = {record["path"]: record for record in registry["sources"]}
    hashes: dict[str, str] = {}
    for relative in inputs:
        record = by_path.get(relative)
        if operation == "ingest" and record is None:
            raise ADWikiError(f"ingest input is not registered: {relative}")
        if record is not None:
            hashes[relative] = record["sha256"]
    return hashes


def _validate_write_targets(
    root: Path,
    bundle: Path,
    raw: Path,
    operation: str,
    write_set: list[str],
) -> None:
    if operation not in WRITABLE_OPERATIONS:
        raise ADWikiError(f"operation does not support staged writes: {operation}")
    if not write_set:
        raise ADWikiError("a writable operation requires a non-empty write set")
    for relative in write_set:
        target = _resolve_inside(root, relative, "write_set path")
        if _path_is_within(target, raw):
            raise ADWikiError(f"write set must never include Raw: {relative}")
        if operation != "migrate" and not _path_is_within(target, bundle):
            raise ADWikiError(f"knowledge write must resolve inside bundle_root: {relative}")
        if operation != "migrate" and target.suffix.lower() != ".md":
            raise ADWikiError(f"knowledge write must target Markdown: {relative}")
        if operation != "migrate" and any(
            part.startswith(".") for part in target.relative_to(bundle).parts
        ):
            raise ADWikiError(f"knowledge write must not target a hidden Bundle path: {relative}")
        if target.name in {"index.md", "log.md"}:
            raise ADWikiError(f"indexes and log are managed by the transaction: {relative}")
        if ".git" in target.parts or _path_is_within(target, root / ".ad-wiki/runs"):
            raise ADWikiError(f"write target is reserved: {relative}")
        if operation == "migrate":
            allowed_control_files = {root / "ad-wiki.yaml", root / ".ad-wiki/domain.md"}
            if target in {
                root / ".ad-wiki/lock",
                root / ".ad-wiki/source-registry.json",
            }:
                raise ADWikiError(f"migration write target is immutable runtime state: {relative}")
            if target not in allowed_control_files and not _path_is_within(target, bundle):
                raise ADWikiError(f"migration write target is outside Profile state: {relative}")


def _validation_evidence(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "errors": len(payload.get("errors", payload.get("violations", []))),
        "name": name,
        "status": "passed" if payload.get("ok") else "failed",
        "warnings": len(payload.get("warnings", [])),
    }


def prepare_run(
    repo: str | os.PathLike[str],
    *,
    run_id: str,
    operation: str,
    risk: str,
    inputs: Iterable[str],
    read_set: Iterable[str],
    write_set: Iterable[str],
) -> dict[str, Any]:
    root = _repository_root(repo)
    raw, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    if operation not in ALLOWED_OPERATIONS:
        raise ADWikiError(f"unsupported operation: {operation}")
    if risk not in ALLOWED_RISKS or risk == "prohibited":
        raise ADWikiError(f"unsupported runnable risk: {risk}")

    normalized_inputs = _validate_run_paths(root, inputs, "input")
    normalized_reads = _validate_run_paths(root, read_set, "read_set")
    normalized_writes = _validate_run_paths(root, write_set, "write_set")
    _validate_write_targets(root, bundle, raw, operation, normalized_writes)
    for relative in [*normalized_inputs, *normalized_reads]:
        path = _resolve_inside(root, relative, "planned read")
        if not path.is_file() or path.is_symlink():
            raise ADWikiError(f"planned input/read must be a regular file: {relative}")
    if operation == "ingest":
        ingest_config = config.get("ingest", {})
        max_batch_size = ingest_config.get("max_batch_size", 1) if isinstance(ingest_config, dict) else 1
        if not normalized_inputs:
            raise ADWikiError("ingest requires at least one registered input")
        if len(normalized_inputs) > max_batch_size:
            raise ADWikiError(
                f"ingest input count exceeds configured max_batch_size {max_batch_size}"
            )
        for relative in normalized_inputs:
            if not _path_is_within(_resolve_inside(root, relative, "ingest input"), raw):
                raise ADWikiError(f"ingest input must resolve inside raw_root: {relative}")

    path = _run_path(root, run_id)
    if path.exists():
        existing = _load_run(root, run_id)
        identity = {
            "operation": operation,
            "risk": risk,
            "inputs": normalized_inputs,
            "read_set": normalized_reads,
            "write_set": normalized_writes,
        }
        if all(existing.get(key) == value for key, value in identity.items()):
            return {**existing, "result": "unchanged"}
        raise ADWikiError(f"run id already belongs to another plan: {run_id}")
    if path.parent.exists() and any(path.parent.iterdir()):
        raise ADWikiError(f"new run directory is not empty: {run_id}")

    preflight = validate_repository(root)
    if not preflight["ok"]:
        codes = ", ".join(item["code"] for item in preflight["errors"])
        raise ADWikiError(f"repository preflight validation failed: {codes}")
    raw_report = guard_raw(root)
    if not raw_report["ok"]:
        raise ADWikiError("Raw guard failed before planning")

    reserved_baseline = [
        "ad-wiki.yaml",
        ".ad-wiki/source-registry.json",
        _relative_posix(bundle / "index.md", root),
        _relative_posix(bundle / "log.md", root),
    ]
    baseline = _baseline(
        root,
        [*normalized_inputs, *normalized_reads, *normalized_writes, *reserved_baseline],
    )
    now = _utc_now()
    report: dict[str, Any] = {
        "applied_set": [],
        "baseline": baseline,
        "created_at": now,
        "events": [
            {"at": now, "state": "DISCOVERED"},
            {"at": now, "state": "PREFLIGHTED"},
            {"at": now, "state": "PLANNED"},
        ],
        "inputs": normalized_inputs,
        "operation": operation,
        "plugin_version": PLUGIN_VERSION,
        "profile_version": str(config.get("profile_version", PROFILE_VERSION)),
        "read_set": normalized_reads,
        "reviews": [],
        "risk": risk,
        "run_id": run_id,
        "source_hashes": _registered_source_hashes(root, normalized_inputs, operation),
        "status": "PLANNED",
        "updated_at": now,
        "validations": [
            _validation_evidence("preflight-bundle", preflight),
            _validation_evidence("preflight-raw", raw_report),
        ],
        "write_set": normalized_writes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "staged").mkdir(parents=True, exist_ok=True)
    _save_run(root, report)
    return {**report, "result": "created", "staging_root": _relative_posix(path.parent / "staged", root)}


def _stage_root(root: Path, run_id: str) -> Path:
    return _run_path(root, run_id).parent / "staged"


def _staged_files(root: Path, report: dict[str, Any]) -> dict[str, Path]:
    stage = _stage_root(root, str(report["run_id"]))
    if not stage.is_dir():
        raise ADWikiError("staging directory is missing")
    actual: dict[str, Path] = {}
    for path in sorted(stage.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not _path_is_within(path.resolve(), stage):
            raise ADWikiError(f"staged path escapes the run: {path}")
        relative = path.relative_to(stage).as_posix()
        actual[relative] = path
    expected = set(report.get("write_set", []))
    missing = sorted(expected - set(actual))
    extra = sorted(set(actual) - expected)
    if missing or extra:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if extra:
            details.append("unplanned: " + ", ".join(extra))
        raise ADWikiError("staged write set does not match the plan (" + "; ".join(details) + ")")
    for relative, path in actual.items():
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ADWikiError(f"staged knowledge must be UTF-8 text: {relative}") from exc
    return actual


def _validate_human_actor(actor: str) -> None:
    if not HUMAN_ACTOR.fullmatch(actor):
        raise ADWikiError(f"review actor must be a real human:<id>: {actor}")


def approve_run(
    repo: str | os.PathLike[str],
    *,
    run_id: str,
    actor: str | None = None,
) -> dict[str, Any]:
    """Return the current run unchanged for legacy callers of the removed approval step."""
    _ = actor
    root = _repository_root(repo)
    report = _load_run(root, run_id)
    return {
        **report,
        "deprecated": True,
        "message": "Pre-apply approval was removed; call apply_run.py directly.",
        "result": "approval_not_required",
    }


@contextmanager
def _repository_lock(root: Path, run_id: str) -> Iterator[None]:
    lock_path = _resolve_inside(root, ".ad-wiki/lock", "lock path")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ADWikiError("another AD-Wiki writer holds .ad-wiki/lock") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"acquired_at": _utc_now(), "pid": os.getpid(), "run_id": run_id}, handle)
            handle.write("\n")
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _rollback_paths(root: Path, bundle: Path, write_set: list[str]) -> set[Path]:
    markdown, _ = _bundle_markdown_files(bundle)
    paths = {path for path in markdown if path.name in {"index.md", "log.md"}}
    paths.update(_resolve_inside(root, relative, "write_set path") for relative in write_set)
    for relative in write_set:
        parent = _resolve_inside(root, relative, "write_set path").parent
        while _path_is_within(parent, bundle):
            paths.add(parent / "index.md")
            if parent == bundle:
                break
            parent = parent.parent
    paths.add(bundle / "log.md")
    return paths


def _snapshot(paths: Iterable[Path], root: Path) -> dict[Path, bytes | None]:
    result: dict[Path, bytes | None] = {}
    for path in paths:
        if path.is_symlink():
            raise ADWikiError(f"transaction target must not be a symlink: {_relative_posix(path, root)}")
        if path.exists() and not path.is_file():
            raise ADWikiError(f"transaction target must be a file: {_relative_posix(path, root)}")
        result[path] = path.read_bytes() if path.exists() else None
    return result


def _restore(snapshot: dict[Path, bytes | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            if path.exists() and path.is_file() and not path.is_symlink():
                path.unlink()
        else:
            _atomic_write_bytes(path, content)


def _prepend_log(
    log_path: Path,
    run_id: str,
    operation: str,
    changed_count: int,
    content_language: str,
) -> None:
    log_title = "知识包更新日志" if content_language == "zh-CN" else "Knowledge Bundle Update Log"
    text = log_path.read_text(encoding="utf-8") if log_path.exists() else f"# {log_title}\n"
    if f"`{run_id}`" in text:
        raise ADWikiError(f"log already contains run id: {run_id}")
    day = _utc_now()[:10]
    heading = f"## {day}"
    entry = (
        f"* **{operation}** `{run_id}`：已应用 {changed_count} 个计划知识文件。"
        if content_language == "zh-CN"
        else f"* **{operation.title()}** `{run_id}`: applied {changed_count} planned knowledge file(s)."
    )
    if heading in text.splitlines():
        lines = text.splitlines()
        index = lines.index(heading) + 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        lines.insert(index, entry)
        content = "\n".join(lines).rstrip() + "\n"
    else:
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            content = "\n".join([lines[0], "", heading, "", entry, "", *lines[1:]]).rstrip() + "\n"
        else:
            content = f"# {log_title}\n\n{heading}\n\n{entry}\n\n{text.lstrip()}"
    _atomic_write_text(log_path, content)


def _mark_failed(root: Path, report: dict[str, Any], message: str, validation: dict[str, Any] | None) -> None:
    report["failure"] = {"at": _utc_now(), "message": message}
    if validation is not None:
        report.setdefault("validations", []).append(_validation_evidence("post-apply-bundle", validation))
    try:
        _advance(report, "FAILED", reason=message)
    except ADWikiError:
        report["status"] = "FAILED"
        report.setdefault("events", []).append({"at": _utc_now(), "state": "FAILED", "reason": message})
    _save_run(root, report)


def apply_run(repo: str | os.PathLike[str], *, run_id: str) -> dict[str, Any]:
    root = _repository_root(repo)
    _, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    report = _load_run(root, run_id)
    if report.get("status") in {"VALIDATED", "REVIEWED"}:
        _check_baseline(root, report.get("baseline_after", {}))
        raw_report = guard_raw(root)
        if not raw_report["ok"]:
            raise ADWikiError("Raw guard failed for the completed run")
        return {**report, "result": "unchanged"}
    if report.get("status") not in {
        "PLANNED",
        "REVIEW_REQUIRED",
        "APPROVED",
        "AUTO_APPROVED",
    }:
        raise ADWikiError(f"run cannot be applied from state: {report.get('status')}")
    staged = _staged_files(root, report)

    with _repository_lock(root, run_id):
        staged_bytes = {
            relative: path.read_bytes() for relative, path in sorted(staged.items())
        }
        staged_hashes = {
            relative: hashlib.sha256(content).hexdigest()
            for relative, content in staged_bytes.items()
        }
        approved_staged_hashes = report.get("approved_staged_hashes")
        if approved_staged_hashes is not None and staged_hashes != approved_staged_hashes:
            raise ADWikiError("staged content changed after recorded approval")
        snapshot: dict[Path, bytes | None] | None = None
        validation: dict[str, Any] | None = None
        try:
            raw_before = guard_raw(root)
            if not raw_before["ok"]:
                raise ADWikiError("Raw guard failed before apply")
            _check_baseline(root, report.get("baseline", {}))
            rollback_paths = _rollback_paths(root, bundle, list(report["write_set"]))
            snapshot = _snapshot(rollback_paths, root)

            for relative, content in staged_bytes.items():
                target = _resolve_inside(root, relative, "write_set path")
                if target.is_symlink():
                    raise ADWikiError(f"write target must not be a symlink: {relative}")
                _atomic_write_bytes(target, content)

            index_result = build_indexes(root)
            _prepend_log(
                bundle / "log.md",
                run_id,
                str(report["operation"]),
                len(staged),
                _content_language(config),
            )
            applied_set = sorted(
                {
                    *report["write_set"],
                    *index_result["changed"],
                    _relative_posix(bundle / "log.md", root),
                }
            )
            report["applied_set"] = applied_set
            report["staged_hashes"] = staged_hashes
            _advance(report, "APPLIED")
            _save_run(root, report)

            validation = validate_repository(root)
            raw_after = guard_raw(root)
            if not validation["ok"]:
                codes = ", ".join(item["code"] for item in validation["errors"])
                raise ADWikiError(f"post-apply Bundle validation failed: {codes}")
            if not raw_after["ok"]:
                raise ADWikiError("Raw guard failed after apply")
            report.setdefault("validations", []).extend(
                [
                    _validation_evidence("post-apply-bundle", validation),
                    _validation_evidence("post-apply-raw", raw_after),
                ]
            )
            report["baseline_after"] = _baseline(
                root,
                [*report.get("baseline", {}), *applied_set],
            )
            _advance(report, "VALIDATED")
            _save_run(root, report)
            return {**report, "result": "applied"}
        except Exception as exc:
            if snapshot is not None:
                _restore(snapshot)
            _mark_failed(root, report, str(exc), validation)
            if isinstance(exc, ADWikiError):
                raise
            raise ADWikiError(f"transaction failed and was rolled back: {exc}") from exc


def review_run(
    repo: str | os.PathLike[str],
    *,
    run_id: str,
    actor: str,
    decision: str,
    note: str | None = None,
) -> dict[str, Any]:
    root = _repository_root(repo)
    _configured_roots(root)
    report = _load_run(root, run_id)
    if report.get("status") == "REVIEWED" and decision == "approved":
        _check_baseline(root, report.get("baseline_after", {}))
        return {**report, "result": "unchanged"}
    if report.get("status") != "VALIDATED":
        raise ADWikiError(f"run cannot be reviewed from state: {report.get('status')}")
    if decision not in {"approved", "rejected"}:
        raise ADWikiError("review decision must be approved or rejected")
    _check_baseline(root, report.get("baseline_after", {}))
    raw_report = guard_raw(root)
    if not raw_report["ok"]:
        raise ADWikiError("Raw guard failed before review")
    _validate_human_actor(actor)
    review = {"at": _utc_now(), "by": actor, "decision": decision}
    if note:
        review["note"] = note
    report.setdefault("reviews", []).append(review)
    _advance(report, "REVIEWED" if decision == "approved" else "FAILED", by=actor, decision=decision)
    _save_run(root, report)
    return {**report, "result": decision}


def _search_tokens(value: str, *, query: bool = False) -> list[str]:
    normalized = value.casefold()
    if query:
        for phrase in sorted(QUERY_NOISE, key=len, reverse=True):
            normalized = normalized.replace(phrase, " ")
    tokens: list[str] = []
    for match in SEARCH_SEGMENT.finditer(normalized):
        segment = match.group(0)
        if not segment:
            continue
        if not ("\u3400" <= segment[0] <= "\u9fff"):
            tokens.append(segment)
            continue
        if len(segment) == 1:
            tokens.append(segment)
            continue
        for size in (2, 3):
            if len(segment) < size:
                continue
            tokens.extend(segment[index : index + size] for index in range(len(segment) - size + 1))
    return tokens


def _query_terms(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            token
            for token in _search_tokens(value, query=True)
            if token not in QUERY_TOKEN_NOISE
            and not (len(token) == 1 and "\u3400" <= token <= "\u9fff")
        )
    )


def _minimum_term_matches(term_count: int) -> int:
    if term_count == 1:
        return 1
    if term_count <= 4:
        return 2
    return 3


def _has_symlink_component(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _normalized_concept_ids(concept_ids: Iterable[str], *, maximum: int = 8) -> list[str]:
    normalized: list[str] = []
    for concept_id in concept_ids:
        if not isinstance(concept_id, str):
            raise ADWikiError("Concept IDs must be strings")
        if concept_id in normalized:
            continue
        normalized.append(concept_id)
    if not normalized:
        raise ADWikiError("at least one --concept is required")
    if len(normalized) > maximum:
        raise ADWikiError(f"at most {maximum} Concepts may be selected")
    return normalized


def _read_bundle_concept(
    bundle: Path,
    concept_id: str,
    *,
    purpose: str,
) -> tuple[Path, str, list[str], str]:
    if (
        not CONCEPT_ID.fullmatch(concept_id)
        or ".." in Path(concept_id).parts
        or concept_id.endswith(".md")
    ):
        raise ADWikiError(f"invalid {purpose} Concept ID: {concept_id}")
    lexical_path = bundle / f"{concept_id}.md"
    if _has_symlink_component(lexical_path, bundle):
        raise ADWikiError(f"{purpose} Concept must not use a symlink: {concept_id}")
    path = _resolve_inside(bundle, f"{concept_id}.md", f"{purpose} Concept")
    bundle_relative = path.relative_to(bundle)
    if (
        path.is_symlink()
        or not path.is_file()
        or path.name in {"index.md", "log.md"}
        or any(part.startswith(".") for part in bundle_relative.parts)
    ):
        raise ADWikiError(f"{purpose} Concept ID is not a readable Bundle Concept: {concept_id}")
    text = path.read_text(encoding="utf-8")
    parsed = _frontmatter(text)
    if not parsed:
        raise ADWikiError(f"{purpose} Concept lacks frontmatter: {concept_id}")
    lines, body = parsed
    return path, text, lines, body


def _selected_concept_sources(
    bundle: Path,
    concept_ids: Iterable[str],
) -> tuple[list[str], list[str]]:
    normalized_ids = _normalized_concept_ids(concept_ids)
    resources: list[str] = []
    for concept_id in normalized_ids:
        _, _, lines, _ = _read_bundle_concept(bundle, concept_id, purpose="Raw fallback")
        fields, _, _ = _top_level(lines)
        for entry in _source_entries(lines, fields.get("sources")):
            resource = entry.get("resource")
            if resource and resource not in resources:
                resources.append(str(resource))
    return normalized_ids, resources


def _registered_records_for_resources(
    root: Path,
    resources: list[str],
) -> list[dict[str, Any]]:
    registry = _load_registry(root)
    resource_set = set(resources)
    latest: dict[str, dict[str, Any]] = {}
    for record in registry["sources"]:
        locator = str(record["canonical_locator"])
        if locator not in resource_set:
            continue
        current = latest.get(locator)
        if current is None or int(record["version"]) > int(current["version"]):
            latest[locator] = record
    records = [latest[resource] for resource in resources if resource in latest]
    if not records:
        raise ADWikiError("selected Concepts have no registered Raw sources")
    return records


def _read_verified_registered_source(root: Path, raw_root: Path, record: dict[str, Any]) -> str:
    lexical_path = root / str(record["path"])
    if _has_symlink_component(lexical_path, root):
        raise ADWikiError(f"registered Raw source must not use a symlink: {record['path']}")
    path = _resolve_inside(root, str(record["path"]), "registered Raw source")
    if not _path_is_within(path, raw_root) or not path.is_file():
        raise ADWikiError(f"registered Raw source is outside raw_root or missing: {record['path']}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ADWikiError(f"registered Raw source changed: {record['path']}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ADWikiError(f"registered Raw source is not UTF-8 text: {record['path']}") from exc


def _raw_excerpt_candidates(text: str, terms: list[str]) -> list[dict[str, Any]]:
    lines = text.splitlines()
    headings = [index for index, line in enumerate(lines) if line.lstrip().startswith("#")]
    ranked: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        counts = Counter(_search_tokens(line))
        matched = sorted(term for term in terms if counts[term] > 0)
        if len(matched) < _minimum_term_matches(len(terms)):
            continue
        previous_headings = [heading for heading in headings if heading <= index]
        next_headings = [heading for heading in headings if heading > index]
        section_start = previous_headings[-1] if previous_headings else max(0, index - 2)
        section_end = next_headings[0] if next_headings else min(len(lines), index + 8)
        if section_end - section_start > 80:
            start = max(0, index - 3)
            end = min(len(lines), index + 9)
        else:
            start = section_start
            end = section_end
        content = "\n".join(lines[start:end]).strip()
        if not content:
            continue
        ranked.append(
            {
                "content": content,
                "end_line": end,
                "matched_terms": matched,
                "score": 10 * len(matched) + sum(counts[term] for term in matched),
                "start_line": start + 1,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["start_line"]))
    selected: list[dict[str, Any]] = []
    for candidate in ranked:
        if any(
            candidate["start_line"] <= existing["end_line"]
            and existing["start_line"] <= candidate["end_line"]
            for existing in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) == 2:
            break
    return selected


def query_registered_raw(
    repo: str | os.PathLike[str],
    *,
    query: str,
    concept_ids: Iterable[str],
    max_sources: int = 2,
    max_chars: int = 6_000,
) -> dict[str, Any]:
    """Build one bounded, read-only Raw fallback context from selected Concept provenance."""
    if not query.strip():
        raise ADWikiError("query must be non-empty")
    if max_sources < 1 or max_sources > 5:
        raise ADWikiError("max-sources must be between 1 and 5")
    if max_chars < 1 or max_chars > 100_000:
        raise ADWikiError("max-chars must be between 1 and 100000")
    terms = _query_terms(query)
    if not terms:
        raise ADWikiError("query has no searchable terms")

    root = _repository_root(repo)
    raw_root, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    normalized_ids, resources = _selected_concept_sources(bundle, concept_ids)
    records = _registered_records_for_resources(root, resources)
    selected_records = records[:max_sources]
    remaining_chars = max_chars
    included_chars = 0
    content_truncated = False
    sources: list[dict[str, Any]] = []
    for record_index, record in enumerate(selected_records):
        text = _read_verified_registered_source(root, raw_root, record)
        candidates = _raw_excerpt_candidates(text, terms)
        excerpts: list[dict[str, Any]] = []
        for candidate_index, candidate in enumerate(candidates):
            if remaining_chars == 0:
                content_truncated = True
                break
            full_content = str(candidate["content"])
            content = full_content[:remaining_chars]
            truncated = len(content) < len(full_content)
            excerpts.append({**candidate, "content": content, "content_truncated": truncated})
            included_chars += len(content)
            remaining_chars -= len(content)
            if truncated:
                content_truncated = True
                break
        if excerpts:
            sources.append(
                {
                    "canonical_locator": record["canonical_locator"],
                    "excerpts": excerpts,
                    "integrity": "verified",
                    "path": record["path"],
                    "registry_source_id": record["source_id"],
                    "version": record["version"],
                }
            )
        if remaining_chars == 0:
            if candidate_index < len(candidates) - 1 or record_index < len(selected_records) - 1:
                content_truncated = True
            break
    return {
        "schema_version": "1",
        "mode": "raw-fallback",
        "query": query,
        "concepts": normalized_ids,
        "retrieval": {
            "content_truncated": content_truncated,
            "included_chars": included_chars,
            "included_source_count": len(sources),
            "linked_source_count": len(records),
            "max_chars": max_chars,
            "max_sources": max_sources,
            "source_limit_reached": len(records) > len(selected_records),
        },
        "sources": sources,
    }


def migrate_repository(
    repo: str | os.PathLike[str],
    *,
    target_profile: str = PROFILE_VERSION,
) -> dict[str, Any]:
    root = _repository_root(repo)
    config = _load_config(root)
    current = str(config.get("profile_version", ""))
    if target_profile != PROFILE_VERSION:
        raise ADWikiError(f"unsupported target profile: {target_profile}")
    if current == target_profile:
        validation = validate_repository(root)
        if not validation["ok"]:
            codes = ", ".join(item["code"] for item in validation["errors"])
            raise ADWikiError(f"current Profile repository is invalid: {codes}")
        return {
            "changed": [],
            "from_profile": current,
            "status": "current",
            "target_profile": target_profile,
            "validation": _validation_evidence("current-profile", validation),
        }
    raise ADWikiError(f"no deterministic migration path from {current or '<missing>'} to {target_profile}")
