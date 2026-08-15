from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .core import (
    ADWikiError,
    ALLOWED_OPERATIONS,
    ALLOWED_RISKS,
    PLUGIN_VERSION,
    PROFILE_VERSION,
    RUN_ID,
    STATE_TRANSITIONS,
    _atomic_write_json,
    _atomic_write_text,
    _bundle_markdown_files,
    _configured_roots,
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
ACTOR = re.compile(r"(?:human|process):[^\s:]+|[^\s/:]+/[^\s/]+")
SEARCH_TERM = re.compile(r"[a-z0-9][a-z0-9_-]*|[\u3400-\u9fff]", re.IGNORECASE)


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
        "approvals": [],
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


def _validate_actor(actor: str) -> None:
    if not ACTOR.fullmatch(actor):
        raise ADWikiError(f"invalid approval/review actor: {actor}")


def _review_owners(config: dict[str, Any]) -> list[str]:
    review = config.get("review", {})
    if not isinstance(review, dict):
        raise ADWikiError("review configuration must be a mapping")
    owners = review.get("owners", [])
    if not isinstance(owners, list) or not all(isinstance(item, str) and ACTOR.fullmatch(item) for item in owners):
        raise ADWikiError("review.owners must be a list of valid actors")
    return owners


def approve_run(
    repo: str | os.PathLike[str],
    *,
    run_id: str,
    actor: str | None = None,
) -> dict[str, Any]:
    root = _repository_root(repo)
    _, _, config = _configured_roots(root)
    report = _load_run(root, run_id)
    if report.get("status") in {"APPROVED", "AUTO_APPROVED"}:
        return {**report, "result": "unchanged"}
    if report.get("status") not in {"PLANNED", "REVIEW_REQUIRED"}:
        raise ADWikiError(f"run cannot be approved from state: {report.get('status')}")
    _check_baseline(root, report.get("baseline", {}))
    staged = _staged_files(root, report)
    risk = report.get("risk")
    if risk == "low":
        approval_actor = actor or "process:ad-wiki"
        _validate_actor(approval_actor)
        state = "AUTO_APPROVED"
    else:
        if actor is None:
            raise ADWikiError(f"{risk}-risk run requires an explicit approval actor")
        _validate_actor(actor)
        owners = _review_owners(config)
        if owners and actor not in owners:
            raise ADWikiError(f"approval actor is not a configured owner: {actor}")
        approval_actor = actor
        state = "APPROVED"
    report.setdefault("approvals", []).append({"at": _utc_now(), "by": approval_actor, "risk": risk})
    report["approved_staged_hashes"] = {
        relative: _sha256_file(path) for relative, path in sorted(staged.items())
    }
    _advance(report, state, by=approval_actor)
    _save_run(root, report)
    return {**report, "result": "approved"}


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


def _prepend_log(log_path: Path, run_id: str, operation: str, changed_count: int) -> None:
    text = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Knowledge Bundle Update Log\n"
    if run_id in text:
        raise ADWikiError(f"log already contains run id: {run_id}")
    day = _utc_now()[:10]
    heading = f"## {day}"
    entry = f"* **{operation.title()}** `{run_id}`: applied {changed_count} planned knowledge file(s)."
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
            content = f"# Knowledge Bundle Update Log\n\n{heading}\n\n{entry}\n\n{text.lstrip()}"
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
    if report.get("status") not in {"APPROVED", "AUTO_APPROVED"}:
        raise ADWikiError(f"run must be approved before apply; current state: {report.get('status')}")
    staged = _staged_files(root, report)
    staged_hashes = {relative: _sha256_file(path) for relative, path in sorted(staged.items())}
    if staged_hashes != report.get("approved_staged_hashes"):
        raise ADWikiError("staged content changed after approval")

    with _repository_lock(root, run_id):
        snapshot: dict[Path, bytes | None] | None = None
        validation: dict[str, Any] | None = None
        try:
            raw_before = guard_raw(root)
            if not raw_before["ok"]:
                raise ADWikiError("Raw guard failed before apply")
            _check_baseline(root, report.get("baseline", {}))
            rollback_paths = _rollback_paths(root, bundle, list(report["write_set"]))
            snapshot = _snapshot(rollback_paths, root)

            for relative, staged_path in staged.items():
                target = _resolve_inside(root, relative, "write_set path")
                if target.is_symlink():
                    raise ADWikiError(f"write target must not be a symlink: {relative}")
                _atomic_write_bytes(target, staged_path.read_bytes())

            index_result = build_indexes(root)
            _prepend_log(bundle / "log.md", run_id, str(report["operation"]), len(staged))
            applied_set = sorted({*report["write_set"], *index_result["changed"], _relative_posix(bundle / "log.md", root)})
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
    _, _, config = _configured_roots(root)
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
    _validate_actor(actor)
    owners = _review_owners(config)
    if report.get("risk") in {"medium", "high"} and owners and actor not in owners:
        raise ADWikiError(f"review actor is not a configured owner: {actor}")
    review = {"at": _utc_now(), "by": actor, "decision": decision}
    if note:
        review["note"] = note
    report.setdefault("reviews", []).append(review)
    _advance(report, "REVIEWED" if decision == "approved" else "FAILED", by=actor, decision=decision)
    _save_run(root, report)
    return {**report, "result": decision}


def _search_tokens(value: str) -> list[str]:
    return SEARCH_TERM.findall(value.casefold())


def search_repository(
    repo: str | os.PathLike[str],
    *,
    query: str,
    limit: int = 10,
) -> dict[str, Any]:
    root = _repository_root(repo)
    _, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    search_config = config.get("search", {})
    if not isinstance(search_config, dict) or search_config.get("provider", "builtin") != "builtin":
        raise ADWikiError("search.provider is not supported by this Plugin runtime")
    if not query.strip():
        raise ADWikiError("query must be non-empty")
    if limit < 1 or limit > 100:
        raise ADWikiError("limit must be between 1 and 100")
    if not (bundle / "index.md").is_file():
        raise ADWikiError("Bundle root index.md is missing")

    terms = _search_tokens(query)
    if not terms:
        raise ADWikiError("query has no searchable terms")
    results: list[dict[str, Any]] = []
    markdown, unsafe = _bundle_markdown_files(bundle)
    if unsafe:
        raise ADWikiError("Bundle contains unsafe Markdown paths")
    for path in markdown:
        if path.name in {"index.md", "log.md"}:
            continue
        text = path.read_text(encoding="utf-8")
        parsed = _frontmatter(text)
        if not parsed:
            continue
        lines, body = parsed
        fields, _, _ = _top_level(lines)
        title = fields.get("title") or path.stem.replace("-", " ").title()
        description = fields.get("description") or ""
        haystacks = {
            "title": " ".join(_search_tokens(title)),
            "description": " ".join(_search_tokens(description)),
            "body": " ".join(_search_tokens(body)),
            "path": path.relative_to(bundle).as_posix().casefold(),
        }
        score = sum(
            6 * haystacks["title"].count(term)
            + 3 * haystacks["description"].count(term)
            + haystacks["body"].count(term)
            + 2 * haystacks["path"].count(term)
            for term in terms
        )
        if query.casefold() in text.casefold():
            score += 8
        if score <= 0:
            continue
        snippet = ""
        for line in body.splitlines():
            if any(term in " ".join(_search_tokens(line)) for term in terms):
                snippet = line.strip()[:240]
                if snippet:
                    break
        sources = [
            {key: entry[key] for key in ("id", "resource", "title") if entry.get(key)}
            for entry in _source_entries(lines, fields.get("sources"))
        ]
        results.append(
            {
                "concept_id": path.relative_to(bundle).with_suffix("").as_posix(),
                "description": description,
                "path": _relative_posix(path, root),
                "score": score,
                "snippet": snippet,
                "sources": sources,
                "title": title,
                "type": fields.get("type") or "",
            }
        )
    results.sort(key=lambda item: (-item["score"], item["path"].casefold()))
    return {
        "bundle": _relative_posix(bundle, root),
        "count": min(len(results), limit),
        "query": query,
        "results": results[:limit],
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
