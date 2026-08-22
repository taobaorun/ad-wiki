from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .core import (
    ADWikiError,
    PLUGIN_VERSION,
    PROFILE_VERSION,
    _bundle_markdown_files,
    _configured_roots,
    _content_language,
    _frontmatter,
    _path_is_within,
    _relative_posix,
    _repository_root,
    _require_supported_profile,
    _sha256_file,
    _top_level,
    _utc_now,
    guard_raw,
    validate_repository,
)
from .runtime import (
    _baseline,
    _check_baseline,
    _load_run,
    _run_path,
    _save_run,
    _validation_evidence,
)
from .code_index.cache import cache_root_for, load_bindings, load_current_index, publish_bindings
from .code_index.model import canonical_json_bytes
from .code_index.query import query_graph


CODE_WIKI_SCHEMA_VERSION = "1"
CODE_WIKI_STATUSES = {
    "pending",
    "enriched",
    "docs-only",
    "no-code-match",
    "needs-review",
    "failed",
    "unchanged",
}
CODE_WIKI_TERMINAL_STATUSES = CODE_WIKI_STATUSES - {"pending"}
CODE_WIKI_FEEDBACK_KINDS = {
    "knowledge-gap",
    "granularity",
    "alias",
    "broken-link",
    "implementation-only",
    "apparent-divergence",
    "confirmed-divergence",
    "suspected-wiki-error",
}
CODE_REF_KINDS = {"implementation", "test", "caller", "configuration"}
STRUCTURAL_EVIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
DENIED_CODE_PARTS = {".git", "build", "dist", "node_modules", "target", "vendor"}
DENIED_CODE_NAMES = {".env", "id_dsa", "id_ed25519", "id_rsa"}
DENIED_CODE_SUFFIXES = {".der", ".jks", ".key", ".p12", ".pfx", ".pem"}
MANAGED_START = "<!-- ad-code-wiki:start -->"
MANAGED_END = "<!-- ad-code-wiki:end -->"
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
)


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


def _normalize_remote(value: str | None) -> str | None:
    if not value:
        return None
    remote = value.strip().rstrip("/")
    scp = re.fullmatch(r"([^/@:]+@[^/:]+):(.+)", remote)
    if scp:
        remote = f"ssh://{scp.group(1)}/{scp.group(2)}"
    if remote.endswith(".git"):
        remote = remote[:-4]
    return remote


def inspect_code_repository(code_repo: str | Path) -> dict[str, Any]:
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
    if revision is None or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ADWikiError("code repository requires a committed HEAD")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise ADWikiError("code repository must be a clean Git worktree")
    remote = _normalize_remote(_git(root, "remote", "get-url", "origin", allow_failure=True))
    root_commits_text = _git(root, "rev-list", "--max-parents=0", "HEAD") or ""
    return {
        "remote": remote,
        "repository": root.name,
        "revision": revision,
        "root_commits": sorted(line for line in root_commits_text.splitlines() if line),
        "worktree_clean": True,
    }


def _has_code_wiki_source_tag(path: Path) -> bool:
    parsed = _frontmatter(path.read_text(encoding="utf-8"))
    if parsed is None:
        return False
    fields, _, _ = _top_level(parsed[0])
    tags = fields.get("tags") or ""
    return "code-wiki-source" in {
        item.strip().strip("\"'")
        for item in tags.strip("[]").split(",")
        if item.strip()
    }


def _frontmatter_tags(fields: dict[str, str | None]) -> set[str]:
    tags = fields.get("tags") or ""
    return {
        item.strip().strip("\"'")
        for item in tags.strip("[]").split(",")
        if item.strip()
    }


def _concept_inventory(root: Path, bundle: Path) -> list[dict[str, Any]]:
    markdown, _ = _bundle_markdown_files(bundle)
    concepts: list[dict[str, Any]] = []
    for path in markdown:
        relative_bundle = path.relative_to(bundle)
        if path.name in {"index.md", "log.md"}:
            continue
        if relative_bundle.parts and relative_bundle.parts[0] == "implementations":
            continue
        if _has_code_wiki_source_tag(path):
            continue
        concept_id = relative_bundle.with_suffix("").as_posix()
        implementation = bundle / "implementations" / relative_bundle
        concepts.append(
            {
                "baseline_sha256": _sha256_file(path),
                "concept_id": concept_id,
                "implementation_path": _relative_posix(implementation, root),
                "path": _relative_posix(path, root),
                "status": "pending",
            }
        )
    return sorted(concepts, key=lambda item: item["path"])


def _source_slug(code_source: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(code_source["repository"]).lower()).strip("-")
    return slug or "code"


def _coverage(total: int) -> dict[str, Any]:
    return {
        "docs_only": 0,
        "enriched": 0,
        "evaluated": 0,
        "failed": 0,
        "inventory_total": total,
        "needs_review": 0,
        "no_code_match": 0,
        "pending": total,
        "quality": "partial",
        "unchanged": 0,
    }


def _inventory_identity(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("baseline_sha256", "concept_id", "implementation_path", "path")
    return [{key: item.get(key) for key in keys} for item in concepts]


def _build_structural_index(root: Path, code_repo: str | Path) -> dict[str, Any]:
    uv = shutil.which("uv")
    if uv is None:
        raise ADWikiError("--structural-index requires uv; install uv and retry")
    plugin_root = Path(__file__).resolve().parents[2]
    command = [
        uv,
        "run",
        "--frozen",
        "--project",
        str(plugin_root / "code-index"),
        "python",
        str(plugin_root / "scripts/build_code_index.py"),
        "--repo",
        str(root),
        "--code-repo",
        str(Path(code_repo).expanduser().resolve()),
        "--json",
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ADWikiError(f"structural code index failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ADWikiError(f"structural code index failed: {detail or 'unknown error'}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ADWikiError("structural code index returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("manifest"), dict):
        raise ADWikiError("structural code index returned an invalid result")
    manifest_bytes = canonical_json_bytes(payload["manifest"])
    return {
        "cache_root": payload["cache_root"],
        "changes": payload.get("changes", {}),
        "enabled": True,
        "graph_sha256": payload["graph_sha256"],
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "metrics": payload.get("metrics", {}),
        "schema_version": "1",
    }


def _structural_graph(root: Path, code_source: dict[str, Any], structural: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cache_root = cache_root_for(root, code_source)
    expected_relative = cache_root.relative_to(root).as_posix()
    if structural.get("cache_root") != expected_relative:
        raise ADWikiError("structural index cache identity does not match Code Wiki run")
    graph, manifest = load_current_index(cache_root)
    if graph.get("revision") != code_source.get("revision"):
        raise ADWikiError("structural index revision does not match Code Wiki run")
    if manifest.get("graph_sha256") != structural.get("graph_sha256"):
        raise ADWikiError("structural graph digest does not match Code Wiki run")
    manifest_sha = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
    if manifest_sha != structural.get("manifest_sha256"):
        raise ADWikiError("structural manifest digest does not match Code Wiki run")
    return graph, manifest


def _reuse_structural_bindings(
    root: Path,
    inventory: list[dict[str, Any]],
    code_source: dict[str, Any],
    structural: dict[str, Any],
) -> None:
    cache_root = cache_root_for(root, code_source)
    try:
        bindings = load_bindings(cache_root)
        graph, _ = _structural_graph(root, code_source, structural)
    except ADWikiError:
        return
    if bindings is None:
        return
    by_id = {item["id"]: item for item in graph["nodes"]}
    changed_paths = set(structural.get("changes", {}).get("added", [])) | set(
        structural.get("changes", {}).get("changed", [])
    ) | set(structural.get("changes", {}).get("deleted", []))
    affected_nodes: set[str] = set()
    for node in graph["nodes"]:
        if node.get("kind") != "file" or node.get("source_file") not in changed_paths:
            continue
        impact = query_graph(
            graph,
            {"mode": "affected", "source_id": node["id"], "max_depth": 3},
        )
        affected_nodes.update(item["id"] for item in impact["nodes"])
    reusable: list[tuple[dict[str, Any], dict[str, Any]]] = []
    stored_concepts = bindings.get("concepts", {})
    for concept in inventory:
        stored = stored_concepts.get(concept["concept_id"])
        if not isinstance(stored, dict) or stored.get("base_sha256") != concept["baseline_sha256"]:
            continue
        symbol_ids = stored.get("symbol_ids", [])
        if any(symbol_id not in by_id or symbol_id in affected_nodes for symbol_id in symbol_ids):
            continue
        if any(by_id[symbol_id].get("source_file") in changed_paths for symbol_id in symbol_ids):
            continue
        implementation_path = stored.get("implementation_path")
        implementation_sha = stored.get("implementation_sha256")
        if implementation_path:
            implementation = root / implementation_path
            if not implementation.is_file() or _sha256_file(implementation) != implementation_sha:
                continue
        reusable.append((concept, stored))
    if inventory and (len(inventory) - len(reusable)) / len(inventory) > 0.60:
        return
    for concept, stored in reusable:
        concept["status"] = "unchanged"
        concept["result"] = stored.get("result", {"reason": "Reused validated structural binding."})
        concept["reused_binding"] = True
        concept["reused_binding_data"] = stored


def prepare_code_wiki(
    repo: str | Path,
    *,
    code_repo: str | Path,
    run_id: str,
    structural_index: bool = False,
) -> dict[str, Any]:
    root = _repository_root(repo)
    _, bundle, config = _configured_roots(root)
    _require_supported_profile(config)
    code_source = inspect_code_repository(code_repo)
    inventory = _concept_inventory(root, bundle)
    if not inventory:
        raise ADWikiError("Code Wiki requires at least one base Concept")
    structural = _build_structural_index(root, code_repo) if structural_index else None
    if structural is not None:
        _reuse_structural_bindings(root, inventory, code_source, structural)

    run_path = _run_path(root, run_id)
    if run_path.exists():
        existing = _load_run(root, run_id)
        existing_code_wiki = existing.get("code_wiki", {})
        identity_matches = (
            existing.get("operation") == "code-wiki"
            and existing_code_wiki.get("schema_version") == CODE_WIKI_SCHEMA_VERSION
            and existing_code_wiki.get("code_source") == code_source
            and existing_code_wiki.get("structural_index") == structural
            and _inventory_identity(existing_code_wiki.get("concepts", []))
            == _inventory_identity(inventory)
        )
        if identity_matches:
            return {**existing, "result": "unchanged"}
        if (
            existing.get("operation") == "code-wiki"
            and existing_code_wiki.get("code_source") == code_source
        ):
            raise ADWikiError("Wiki Concept inventory or baseline changed for existing run")
        raise ADWikiError(f"run id already belongs to another plan: {run_id}")
    if run_path.parent.exists() and any(run_path.parent.iterdir()):
        raise ADWikiError(f"new run directory is not empty: {run_id}")

    preflight = validate_repository(root)
    if not preflight["ok"]:
        codes = ", ".join(item["code"] for item in preflight["errors"])
        raise ADWikiError(f"repository preflight validation failed: {codes}")
    raw_report = guard_raw(root)
    if not raw_report["ok"]:
        raise ADWikiError("Raw guard failed before Code Wiki planning")

    source_summary_path = _relative_posix(
        bundle
        / "sources"
        / f"code-{_source_slug(code_source)}-{str(code_source['revision'])[:12]}.md",
        root,
    )
    read_set = [item["path"] for item in inventory]
    potential_writes = [
        *read_set,
        *(item["implementation_path"] for item in inventory),
        source_summary_path,
    ]
    reserved = [
        "ad-wiki.yaml",
        ".ad-wiki/source-registry.json",
        _relative_posix(bundle / "index.md", root),
        _relative_posix(bundle / "log.md", root),
    ]
    now = _utc_now()
    report: dict[str, Any] = {
        "applied_set": [],
        "baseline": _baseline(root, [*potential_writes, *reserved]),
        "code_wiki": {
            "code_source": code_source,
            "concepts": inventory,
            "coverage": _coverage(len(inventory)),
            "finalized": False,
            "schema_version": CODE_WIKI_SCHEMA_VERSION,
            "source_summary_path": source_summary_path,
            "structural_index": structural,
        },
        "created_at": now,
        "events": [
            {"at": now, "state": "DISCOVERED"},
            {"at": now, "state": "PREFLIGHTED"},
            {"at": now, "state": "PLANNED"},
        ],
        "inputs": [],
        "operation": "code-wiki",
        "plugin_version": PLUGIN_VERSION,
        "profile_version": str(config.get("profile_version", PROFILE_VERSION)),
        "read_set": read_set,
        "reviews": [],
        "risk": "medium",
        "run_id": run_id,
        "source_hashes": {},
        "status": "PLANNED",
        "updated_at": now,
        "validations": [
            _validation_evidence("preflight-bundle", preflight),
            _validation_evidence("preflight-raw", raw_report),
        ],
        "write_set": [],
    }
    report["code_wiki"]["coverage"] = _recompute_coverage(report["code_wiki"])
    run_path.parent.mkdir(parents=True, exist_ok=True)
    (run_path.parent / "staged").mkdir(parents=True, exist_ok=True)
    _save_run(root, report)
    return {
        **report,
        "result": "created",
        "staging_root": _relative_posix(run_path.parent / "staged", root),
    }


def _require_code_wiki_run(root: Path, run_id: str) -> dict[str, Any]:
    report = _load_run(root, run_id)
    code_wiki = report.get("code_wiki")
    if (
        report.get("operation") != "code-wiki"
        or not isinstance(code_wiki, dict)
        or code_wiki.get("schema_version") != CODE_WIKI_SCHEMA_VERSION
    ):
        raise ADWikiError(f"run is not a Code Wiki run: {run_id}")
    if report.get("status") != "PLANNED":
        raise ADWikiError(f"Code Wiki run is not editable from state: {report.get('status')}")
    return report


@contextmanager
def _run_lock(root: Path, run_id: str) -> Iterator[None]:
    lock = _run_path(root, run_id).parent / "checkpoint.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ADWikiError(f"another writer is updating Code Wiki run: {run_id}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _same_code_source(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    if expected != actual:
        raise ADWikiError("code repository HEAD, remote, or clean status changed after Prepare")


def _code_ref(
    code_root: Path,
    value: Any,
    structural_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ADWikiError("each code_refs entry must be an object")
    path_value = value.get("path")
    symbol = value.get("symbol")
    kind = value.get("kind")
    if not isinstance(path_value, str) or not path_value or Path(path_value).is_absolute() or ".." in Path(path_value).parts:
        raise ADWikiError("code_refs path must be repository-relative")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ADWikiError("code_refs symbol must be non-empty")
    if kind not in CODE_REF_KINDS:
        raise ADWikiError("code_refs kind is unsupported")
    relative_path = Path(path_value)
    if (
        any(part in DENIED_CODE_PARTS for part in relative_path.parts)
        or relative_path.name in DENIED_CODE_NAMES
        or relative_path.suffix.lower() in DENIED_CODE_SUFFIXES
    ):
        raise ADWikiError(f"code_refs path is generated, vendored, or sensitive: {path_value}")
    unresolved = code_root / path_value
    if unresolved.is_symlink():
        raise ADWikiError(f"code_refs path must not use a symlink: {path_value}")
    resolved = unresolved.resolve()
    if not _path_is_within(resolved, code_root) or not resolved.is_file():
        raise ADWikiError(f"code_refs path is not a regular file inside code repository: {path_value}")
    normalized: dict[str, Any] = {
        "kind": kind,
        "path": Path(path_value).as_posix(),
        "symbol": symbol.strip(),
    }
    if structural_graph is not None:
        symbol_id = value.get("symbol_id")
        evidence = value.get("evidence")
        relation = value.get("relation")
        location = value.get("source_location")
        if not isinstance(symbol_id, str) or not symbol_id:
            raise ADWikiError("structural code_ref requires symbol_id")
        by_id = {item["id"]: item for item in structural_graph["nodes"]}
        node = by_id.get(symbol_id)
        if node is None:
            raise ADWikiError(f"structural code_ref symbol_id is absent from graph: {symbol_id}")
        if node.get("source_file") != normalized["path"]:
            raise ADWikiError("structural code_ref path does not match graph node")
        if normalized["symbol"] not in {node.get("label"), node.get("qualified_name")}:
            raise ADWikiError("structural code_ref symbol does not match graph node")
        if location != node.get("source_location"):
            raise ADWikiError("structural code_ref source_location does not match graph node")
        if evidence not in STRUCTURAL_EVIDENCE:
            raise ADWikiError("structural code_ref evidence is invalid")
        if relation is not None:
            matching_edges = [
                item
                for item in structural_graph["edges"]
                if symbol_id in {item["source"], item["target"]}
                and item["relation"] == relation
                and item["evidence"] == evidence
            ]
            if not matching_edges:
                raise ADWikiError("structural code_ref relation/evidence is absent from graph")
        normalized.update(
            {
                "evidence": evidence,
                "relation": relation,
                "source_location": location,
                "symbol_id": symbol_id,
            }
        )
    return normalized


def _feedback(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ADWikiError("each feedback entry must be an object")
    kind = value.get("kind")
    summary = value.get("summary")
    if kind not in CODE_WIKI_FEEDBACK_KINDS:
        raise ADWikiError("feedback kind is unsupported")
    if not isinstance(summary, str) or not summary.strip():
        raise ADWikiError("feedback summary must be non-empty")
    return {"kind": kind, "summary": summary.strip()}


def _staged_path(root: Path, run_id: str, relative: str) -> Path:
    stage = _run_path(root, run_id).parent / "staged"
    target = stage / relative
    if target.is_symlink() or not _path_is_within(target.resolve(), stage.resolve()):
        raise ADWikiError(f"staged path escapes the run or uses a symlink: {relative}")
    return target


def _normalize_result(
    root: Path,
    code_root: Path,
    run_id: str,
    concept: dict[str, Any],
    status: str,
    result: Any,
    structural_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in CODE_WIKI_TERMINAL_STATUSES:
        raise ADWikiError("Code Wiki checkpoint status must be terminal")
    if not isinstance(result, dict):
        raise ADWikiError("Code Wiki checkpoint result must be an object")
    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ADWikiError("Code Wiki checkpoint reason must be non-empty")
    refs = [_code_ref(code_root, item, structural_graph) for item in result.get("code_refs", [])]
    feedback = [_feedback(item) for item in result.get("feedback", [])]
    normalized: dict[str, Any] = {
        "code_refs": refs,
        "feedback": feedback,
        "reason": reason.strip(),
    }
    if structural_graph is not None:
        vocab = set(structural_graph.get("vocab", []))
        query_tokens = result.get("query_tokens", [])
        matched_node_ids = result.get("matched_node_ids", [])
        if not isinstance(query_tokens, list) or not all(
            isinstance(item, str) and item in vocab for item in query_tokens
        ):
            raise ADWikiError("structural query_tokens must come from graph vocabulary")
        graph_ids = {item["id"] for item in structural_graph["nodes"]}
        if not isinstance(matched_node_ids, list) or not all(
            isinstance(item, str) and item in graph_ids for item in matched_node_ids
        ):
            raise ADWikiError("structural matched_node_ids must exist in graph")
        normalized["matched_node_ids"] = sorted(set(matched_node_ids))
        normalized["query_tokens"] = list(dict.fromkeys(query_tokens))
    implementation_path = result.get("implementation_path")
    if status == "enriched":
        expected = concept["implementation_path"]
        if implementation_path != expected:
            raise ADWikiError(f"enriched result must use implementation_path: {expected}")
        if not any(item["kind"] == "implementation" for item in refs):
            raise ADWikiError("enriched result requires an implementation code ref")
        staged = _staged_path(root, run_id, expected)
        if not staged.is_file():
            raise ADWikiError(f"enriched staged Companion is missing: {expected}")
        normalized["implementation_path"] = expected
    elif implementation_path is not None:
        raise ADWikiError("only enriched results may set implementation_path")
    return normalized


def _recompute_coverage(code_wiki: dict[str, Any]) -> dict[str, Any]:
    concepts = code_wiki.get("concepts", [])
    counts = {status: 0 for status in CODE_WIKI_STATUSES}
    for concept in concepts:
        status = concept.get("status")
        if status not in counts:
            raise ADWikiError(f"invalid Code Wiki Concept status: {status}")
        counts[status] += 1
    pending = counts["pending"]
    complete = pending == 0 and counts["needs-review"] == 0 and counts["failed"] == 0 and counts["no-code-match"] == 0
    return {
        "docs_only": counts["docs-only"],
        "enriched": counts["enriched"],
        "evaluated": len(concepts) - pending,
        "failed": counts["failed"],
        "inventory_total": len(concepts),
        "needs_review": counts["needs-review"],
        "no_code_match": counts["no-code-match"],
        "pending": pending,
        "quality": "complete" if complete else "partial",
        "unchanged": counts["unchanged"],
    }


def checkpoint_code_wiki(
    repo: str | Path,
    *,
    code_repo: str | Path,
    run_id: str,
    concept_id: str,
    status: str,
    result: Any,
    retry: bool = False,
) -> dict[str, Any]:
    root = _repository_root(repo)
    code_root = Path(code_repo).expanduser().resolve()
    code_source = inspect_code_repository(code_repo)
    with _run_lock(root, run_id):
        report = _require_code_wiki_run(root, run_id)
        code_wiki = report["code_wiki"]
        if code_wiki.get("finalized"):
            raise ADWikiError("finalized Code Wiki run cannot be checkpointed")
        _same_code_source(code_wiki["code_source"], code_source)
        structural_graph = None
        structural = code_wiki.get("structural_index")
        if isinstance(structural, dict) and structural.get("enabled"):
            structural_graph, _ = _structural_graph(root, code_source, structural)
        concept = next(
            (item for item in code_wiki.get("concepts", []) if item.get("concept_id") == concept_id),
            None,
        )
        if concept is None:
            raise ADWikiError(f"Concept is not in Code Wiki inventory: {concept_id}")
        normalized = _normalize_result(
            root,
            code_root,
            run_id,
            concept,
            status,
            result,
            structural_graph,
        )
        existing_result = concept.get("result")
        existing_status = concept.get("status")
        if existing_status == status and existing_result == normalized:
            return {**report, "result": "unchanged"}
        if existing_status != "pending" and not retry:
            raise ADWikiError("changing a terminal Code Wiki result requires --retry")
        if retry and existing_status != "pending":
            report.setdefault("events", []).append(
                {
                    "at": _utc_now(),
                    "concept_id": concept_id,
                    "event": "code-wiki-retry",
                    "from": existing_status,
                    "to": status,
                }
            )
        if retry and existing_status == "enriched" and status != "enriched":
            for relative in (str(concept["path"]), str(concept["implementation_path"])):
                obsolete = _staged_path(root, run_id, relative)
                if obsolete.exists():
                    if not obsolete.is_file():
                        raise ADWikiError(f"obsolete staged Code Wiki path is not a file: {relative}")
                    obsolete.unlink()
        concept["result"] = normalized
        concept["status"] = status
        concept["updated_at"] = _utc_now()
        code_wiki["coverage"] = _recompute_coverage(code_wiki)
        report.setdefault("events", []).append(
            {
                "at": _utc_now(),
                "concept_id": concept_id,
                "event": "code-wiki-checkpoint",
                "status": status,
            }
        )
        _save_run(root, report)
        return {**report, "result": "checkpointed"}


def _actual_staged_files(root: Path, run_id: str) -> dict[str, Path]:
    stage = _run_path(root, run_id).parent / "staged"
    if not stage.is_dir():
        raise ADWikiError("Code Wiki staging directory is missing")
    actual: dict[str, Path] = {}
    for path in sorted(stage.rglob("*")):
        if path.is_dir():
            continue
        if path.is_symlink() or not _path_is_within(path.resolve(), stage.resolve()):
            raise ADWikiError(f"staged path escapes the run: {path}")
        relative = path.relative_to(stage).as_posix()
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ADWikiError(f"staged knowledge must be UTF-8 text: {relative}") from exc
        actual[relative] = path
    return actual


def _validate_managed_pair(
    root: Path,
    bundle: Path,
    run_id: str,
    concept: dict[str, Any],
) -> None:
    base = _staged_path(root, run_id, concept["path"])
    implementation = _staged_path(root, run_id, concept["implementation_path"])
    base_text = base.read_text(encoding="utf-8")
    implementation_text = implementation.read_text(encoding="utf-8")
    live_text = (root / concept["path"]).read_text(encoding="utf-8")
    if live_text.count(MANAGED_START) != live_text.count(MANAGED_END) or live_text.count(MANAGED_START) > 1:
        raise ADWikiError(f"live Concept has damaged or duplicate managed markers: {concept['path']}")
    if base_text.count(MANAGED_START) != 1 or base_text.count(MANAGED_END) != 1:
        raise ADWikiError(f"managed implementation link block is invalid: {concept['path']}")
    implementation_link = "/" + (root / concept["implementation_path"]).relative_to(bundle).as_posix()
    base_link = "/" + (root / concept["path"]).relative_to(bundle).as_posix()
    if f"]({implementation_link})" not in base_text:
        raise ADWikiError(f"managed implementation link target is missing: {concept['path']}")
    if f"]({base_link})" not in implementation_text:
        raise ADWikiError(f"implementation Companion must link to base Concept: {concept['implementation_path']}")
    managed = re.compile(
        re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END),
        re.DOTALL,
    )
    if managed.sub("", base_text).rstrip() != managed.sub("", live_text).rstrip():
        raise ADWikiError(f"Code Wiki may only change the managed link block: {concept['path']}")


def _reject_sensitive_content(text: str, relative: str) -> None:
    if re.search(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)", text):
        raise ADWikiError(f"Code Wiki content contains an absolute local path: {relative}")
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise ADWikiError(f"Code Wiki content contains suspected secret material: {relative}")


def _validate_companion(
    path: Path,
    relative: str,
    concept: dict[str, Any],
    revision: str,
    content_language: str,
) -> None:
    text = path.read_text(encoding="utf-8")
    _reject_sensitive_content(text, relative)
    parsed = _frontmatter(text)
    if parsed is None:
        raise ADWikiError(f"implementation Companion requires frontmatter: {relative}")
    lines, body = parsed
    fields, duplicates, malformed = _top_level(lines)
    if duplicates or malformed or fields.get("type") != "Concept":
        raise ADWikiError(f"implementation Companion frontmatter is invalid: {relative}")
    if not {"code-wiki", "implementation"}.issubset(_frontmatter_tags(fields)):
        raise ADWikiError(f"implementation Companion requires code-wiki and implementation tags: {relative}")
    headings = (
        ("## 代码快照", "## 对外契约", "## 实现原理", "## 运行流程", "## 核心代码", "## 关键符号与调用方", "## 相关测试", "## 文档与代码关系", "## 不确定性与继续阅读")
        if content_language == "zh-CN"
        else ("## Code snapshot", "## Public contract", "## Implementation principles", "## Runtime flow", "## Core source", "## Key symbols and callers", "## Related tests", "## Documentation and code relationship", "## Uncertainty and continued reading")
    )
    missing_headings = [heading for heading in headings if heading not in body]
    if missing_headings:
        raise ADWikiError(f"implementation Companion is missing required sections: {relative}")
    if revision not in body:
        raise ADWikiError(f"implementation Companion must include the full code revision: {relative}")
    if "```mermaid" not in body and "无需流程图：" not in body and "Diagram not required:" not in body:
        raise ADWikiError(f"implementation Companion requires Mermaid or a no-diagram rationale: {relative}")
    if not re.search(r"```(?!mermaid)[A-Za-z0-9_+.-]*\n.+?\n```", body, re.DOTALL):
        raise ADWikiError(f"implementation Companion requires a bounded source code block: {relative}")
    result = concept.get("result", {})
    for ref in result.get("code_refs", []):
        if ref["path"] not in body or ref["symbol"] not in body:
            raise ADWikiError(f"implementation Companion is missing checkpointed code ref: {relative}")
    if any(ref["kind"] == "test" for ref in result.get("code_refs", [])):
        disclosure = "未执行" if content_language == "zh-CN" else "did not execute"
        if disclosure not in body:
            raise ADWikiError(f"implementation Companion must disclose that tests were not executed: {relative}")


def finalize_code_wiki(
    repo: str | Path,
    *,
    code_repo: str | Path,
    run_id: str,
) -> dict[str, Any]:
    root = _repository_root(repo)
    _, bundle, config = _configured_roots(root)
    code_source = inspect_code_repository(code_repo)
    with _run_lock(root, run_id):
        report = _require_code_wiki_run(root, run_id)
        code_wiki = report["code_wiki"]
        _same_code_source(code_wiki["code_source"], code_source)
        if code_wiki.get("finalized"):
            return {**report, "result": "unchanged"}
        coverage = _recompute_coverage(code_wiki)
        if coverage["pending"]:
            raise ADWikiError(f"Code Wiki run still has {coverage['pending']} pending Concept(s)")
        _check_baseline(root, report.get("baseline", {}))

        expected = {str(code_wiki["source_summary_path"])}
        for concept in code_wiki.get("concepts", []):
            if concept.get("status") != "enriched":
                continue
            expected.add(str(concept["path"]))
            expected.add(str(concept["implementation_path"]))
        actual = _actual_staged_files(root, run_id)
        missing = sorted(expected - set(actual))
        extra = sorted(set(actual) - expected)
        if missing or extra:
            details = []
            if missing:
                details.append("missing staged: " + ", ".join(missing))
            if extra:
                details.append("unplanned staged: " + ", ".join(extra))
            raise ADWikiError("Code Wiki staged set is invalid (" + "; ".join(details) + ")")
        for concept in code_wiki.get("concepts", []):
            if concept.get("status") == "enriched":
                _validate_managed_pair(root, bundle, run_id, concept)
        source_text = actual[str(code_wiki["source_summary_path"])].read_text(encoding="utf-8")
        if "code-wiki-source" not in source_text or "coverage: partial" not in source_text:
            raise ADWikiError("Code Wiki source summary requires code-wiki-source and coverage: partial")
        if str(code_wiki["code_source"]["revision"]) not in source_text:
            raise ADWikiError("Code Wiki source summary requires the full code revision")
        _reject_sensitive_content(source_text, str(code_wiki["source_summary_path"]))
        for concept in code_wiki.get("concepts", []):
            if concept.get("status") == "enriched":
                _validate_companion(
                    actual[str(concept["implementation_path"])],
                    str(concept["implementation_path"]),
                    concept,
                    str(code_wiki["code_source"]["revision"]),
                    _content_language(config),
                )

        hashes = {
            relative: hashlib.sha256(path.read_bytes()).hexdigest()
            for relative, path in sorted(actual.items())
        }
        feedback: list[dict[str, str]] = []
        seen_feedback: set[tuple[str, str, str]] = set()
        for concept in code_wiki.get("concepts", []):
            for item in concept.get("result", {}).get("feedback", []):
                identity = (str(concept["concept_id"]), str(item["kind"]), str(item["summary"]))
                if identity in seen_feedback:
                    continue
                seen_feedback.add(identity)
                feedback.append(
                    {
                        "concept_id": identity[0],
                        "kind": identity[1],
                        "summary": identity[2],
                    }
                )
        code_wiki["coverage"] = coverage
        code_wiki["feedback"] = feedback
        structural = code_wiki.get("structural_index")
        if isinstance(structural, dict) and structural.get("enabled"):
            binding_concepts: dict[str, Any] = {}
            for concept in code_wiki.get("concepts", []):
                reused = concept.get("reused_binding_data")
                if concept.get("status") == "unchanged" and isinstance(reused, dict):
                    binding_concepts[concept["concept_id"]] = reused
                    continue
                result = concept.get("result", {})
                implementation_path = result.get("implementation_path")
                implementation_sha = (
                    hashes.get(str(implementation_path)) if implementation_path else None
                )
                binding_concepts[concept["concept_id"]] = {
                    "base_sha256": hashes.get(
                        str(concept["path"]), concept["baseline_sha256"]
                    ),
                    "implementation_path": implementation_path,
                    "implementation_sha256": implementation_sha,
                    "result": result,
                    "status": concept["status"],
                    "symbol_ids": sorted(
                        {
                            item["symbol_id"]
                            for item in result.get("code_refs", [])
                            if item.get("symbol_id")
                        }
                    ),
                }
            pending_bindings = {
                "schema_version": "1",
                "revision": code_wiki["code_source"]["revision"],
                "graph_sha256": structural["graph_sha256"],
                "concepts": dict(sorted(binding_concepts.items())),
            }
            code_wiki["pending_bindings"] = pending_bindings
            code_wiki["pending_bindings_sha256"] = hashlib.sha256(
                canonical_json_bytes(pending_bindings)
            ).hexdigest()
        code_wiki["finalized"] = True
        code_wiki["finalized_staged_hashes"] = hashes
        code_wiki["finalized_at"] = _utc_now()
        report["write_set"] = sorted(expected)
        report.setdefault("events", []).append(
            {"at": _utc_now(), "event": "code-wiki-finalized", "write_count": len(expected)}
        )
        _save_run(root, report)
        return {**report, "result": "finalized"}


def publish_code_wiki_bindings(repo: str | Path, *, run_id: str) -> dict[str, Any]:
    root = _repository_root(repo)
    with _run_lock(root, run_id):
        report = _load_run(root, run_id)
        if report.get("operation") != "code-wiki" or report.get("status") != "VALIDATED":
            raise ADWikiError("Code Wiki bindings require a VALIDATED run")
        code_wiki = report.get("code_wiki")
        if not isinstance(code_wiki, dict):
            raise ADWikiError("Code Wiki run metadata is missing")
        structural = code_wiki.get("structural_index")
        bindings = code_wiki.get("pending_bindings")
        if not isinstance(structural, dict) or not structural.get("enabled") or not isinstance(bindings, dict):
            raise ADWikiError("Code Wiki run has no structural bindings to publish")
        expected = hashlib.sha256(canonical_json_bytes(bindings)).hexdigest()
        if expected != code_wiki.get("pending_bindings_sha256"):
            raise ADWikiError("Code Wiki pending bindings changed after Finalize")
        _structural_graph(root, code_wiki["code_source"], structural)
        result = publish_bindings(cache_root_for(root, code_wiki["code_source"]), bindings)
        if code_wiki.get("bindings_published_sha256") == result["bindings_sha256"]:
            return {**report, **result, "result": "unchanged"}
        code_wiki["bindings_published_sha256"] = result["bindings_sha256"]
        code_wiki["bindings_published_at"] = _utc_now()
        report.setdefault("events", []).append(
            {"at": _utc_now(), "event": "code-wiki-bindings-published"}
        )
        _save_run(root, report)
        return {**report, **result, "result": "published"}
