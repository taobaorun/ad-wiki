from __future__ import annotations

import json
import hashlib
import math
import re
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .code_index.cache import cache_root_for, load_bindings, load_current_index
from .code_wiki import MANAGED_START, inspect_code_repository
from .core import (
    ADWikiError,
    FOOTNOTE,
    MARKDOWN_LINK,
    PLUGIN_VERSION,
    _bundle_markdown_files,
    _configured_roots,
    _frontmatter,
    _load_registry,
    _path_is_within,
    _repository_root,
    _source_entries,
    _top_level,
    _utc_now,
    guard_raw,
    validate_repository,
)


HEALTH_SCHEMA_VERSION = "1"
ASSESSMENT_SCHEMA_VERSION = "1"
MAX_ASSESSMENT_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 10_000
MAX_ITEM_VALUES = 100
MAX_TEXT = 1_000
DIMENSIONS = (
    "entry",
    "boundary",
    "mechanism",
    "dependencies",
    "primary_sources",
    "cross_links",
)
OUTCOMES = {
    "compiled-hit",
    "source-descent",
    "knowledge-gap",
    "wrong-answer",
    "wrong-navigation",
}
CITATION_DEPTHS = {"root", "document", "section", "code"}
VISIBILITY = {"none", "visible", "silent"}
METRIC_IDS = (
    "active-code-coverage",
    "ambiguity-visibility",
    "broken-managed-links",
    "citation-depth",
    "citation-validity",
    "code-wiki-concept-evaluation",
    "conflict-visibility",
    "evidence-descent-success",
    "glossary-coverage",
    "index-drift",
    "invalid-code-references",
    "key-system-coverage",
    "orphan-rate",
    "path-compression-gain",
    "primary-source-coverage",
    "representative-question-success",
    "silent-detected-conflicts",
    "snapshot-consistency",
    "source-code-snapshot-freshness",
    "source-integrity",
    "source-to-concept-yield",
    "stale-rate",
    "toc-completeness",
    "unknown-unknown-risk-signals",
    "user-usefulness",
    "wiki-repository-scale-relationship",
)
ALWAYS_GATES = {"source-integrity", "citation-validity", "broken-managed-links"}
ASSESSMENT_GATES = {"snapshot-consistency", "silent-detected-conflicts"}
CODE_GATES = {"code-wiki-concept-evaluation", "invalid-code-references"}
ASSESSMENT_FIELDS = {
    "schema_version",
    "wiki_revision",
    "wiki_digest",
    "code_revision",
    "key_systems",
    "canonical_terms",
    "material_claims",
    "snapshot_consistent",
    "detected_conflicts",
    "representative_questions",
    "scale_points",
    "feedback",
}


def _unknown_fields(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ADWikiError(f"{label} has unknown field: {unknown[0]}")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise ADWikiError(f"{label} must be non-empty text up to {MAX_TEXT} characters")
    return value


def _text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_ITEM_VALUES:
        raise ADWikiError(f"{label} must be a list with at most {MAX_ITEM_VALUES} items")
    return [_text(item, f"{label} item") for item in value]


def _relative_paths(value: Any, label: str) -> list[str]:
    result = _text_list(value, label)
    for item in result:
        path = PurePosixPath(item.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", item):
            raise ADWikiError(f"{label} items must be repository-relative paths")
    return result


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ADWikiError(f"{label} must be boolean")
    return value


def _number(value: Any, label: str, *, nullable: bool = False) -> int | float | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or not math.isfinite(value):
        raise ADWikiError(f"{label} must be a non-negative finite number")
    return value


def _integer(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ADWikiError(f"{label} must be a non-negative integer")
    return value


def _require_unique(values: Iterable[str], label: str, *, casefold: bool = False) -> None:
    normalized = [value.casefold() if casefold else value for value in values]
    if len(normalized) != len(set(normalized)):
        raise ADWikiError(f"{label} must be unique")


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or len(value) > MAX_ITEMS:
        raise ADWikiError(f"{label} must be a list with at most {MAX_ITEMS} items")
    return value


def _validate_journey(value: Any, label: str) -> dict[str, int | float]:
    if not isinstance(value, dict):
        raise ADWikiError(f"{label} must be an object")
    allowed = {"steps", "files", "input_tokens", "time_ms", "wrong_turns"}
    _unknown_fields(value, allowed, label)
    if set(value) != allowed:
        raise ADWikiError(f"{label} requires: " + ", ".join(sorted(allowed)))
    return {key: _number(value[key], f"{label}.{key}") for key in sorted(allowed)}


def _validate_assessment(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ADWikiError("Wiki health assessment must be an object")
    _unknown_fields(value, ASSESSMENT_FIELDS, "Wiki health assessment")
    missing = sorted(ASSESSMENT_FIELDS - set(value))
    if missing:
        raise ADWikiError(f"Wiki health assessment missing field: {missing[0]}")
    if value.get("schema_version") != ASSESSMENT_SCHEMA_VERSION:
        raise ADWikiError(f"Wiki health assessment schema_version must be {ASSESSMENT_SCHEMA_VERSION}")
    wiki_revision = _text(value["wiki_revision"], "wiki_revision")
    wiki_digest = _text(value["wiki_digest"], "wiki_digest")
    code_revision = None if value["code_revision"] is None else _text(value["code_revision"], "code_revision")
    if wiki_revision != "unborn" and not re.fullmatch(r"[0-9a-f]{40}", wiki_revision):
        raise ADWikiError("wiki_revision must be unborn or a full Git commit SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", wiki_digest):
        raise ADWikiError("wiki_digest must be a SHA-256 digest")
    if code_revision is not None and not re.fullmatch(r"[0-9a-f]{40}", code_revision):
        raise ADWikiError("code_revision must be null or a full Git commit SHA")
    feedback = _list(value["feedback"], "feedback")
    if feedback:
        raise ADWikiError("feedback must be empty; use representative_questions.user_feedback without prompt text")
    result: dict[str, Any] = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "wiki_revision": wiki_revision,
        "wiki_digest": wiki_digest,
        "code_revision": code_revision,
        "snapshot_consistent": _bool(value["snapshot_consistent"], "snapshot_consistent"),
        "detected_conflicts": _integer(value["detected_conflicts"], "detected_conflicts"),
        "feedback": [],
    }

    systems: list[dict[str, Any]] = []
    for index, item in enumerate(_list(value["key_systems"], "key_systems")):
        label = f"key_systems[{index}]"
        if not isinstance(item, dict):
            raise ADWikiError(f"{label} must be an object")
        allowed = {"id", "evidence", "concept_ids", "dimensions"}
        _unknown_fields(item, allowed, label)
        if set(item) != allowed or not isinstance(item.get("dimensions"), dict):
            raise ADWikiError(f"{label} has invalid required fields")
        _unknown_fields(item["dimensions"], set(DIMENSIONS), f"{label}.dimensions")
        if set(item["dimensions"]) != set(DIMENSIONS):
            raise ADWikiError(f"{label}.dimensions requires every ToC dimension")
        systems.append(
            {
                "id": _text(item["id"], f"{label}.id"),
                "evidence": _relative_paths(item["evidence"], f"{label}.evidence"),
                "concept_ids": _text_list(item["concept_ids"], f"{label}.concept_ids"),
                "dimensions": {key: _bool(item["dimensions"][key], f"{label}.dimensions.{key}") for key in DIMENSIONS},
            }
        )
    result["key_systems"] = systems
    _require_unique((item["id"] for item in systems), "key system IDs")

    terms: list[dict[str, Any]] = []
    for index, item in enumerate(_list(value["canonical_terms"], "canonical_terms")):
        label = f"canonical_terms[{index}]"
        if not isinstance(item, dict):
            raise ADWikiError(f"{label} must be an object")
        allowed = {"term", "evidence", "defined", "consistent", "aliases"}
        _unknown_fields(item, allowed, label)
        if set(item) != allowed:
            raise ADWikiError(f"{label} has invalid required fields")
        terms.append(
            {
                "term": _text(item["term"], f"{label}.term"),
                "evidence": _relative_paths(item["evidence"], f"{label}.evidence"),
                "defined": _bool(item["defined"], f"{label}.defined"),
                "consistent": _bool(item["consistent"], f"{label}.consistent"),
                "aliases": _text_list(item["aliases"], f"{label}.aliases"),
            }
        )
    result["canonical_terms"] = terms
    _require_unique((item["term"] for item in terms), "canonical terms", casefold=True)

    claims: list[dict[str, Any]] = []
    for index, item in enumerate(_list(value["material_claims"], "material_claims")):
        label = f"material_claims[{index}]"
        if not isinstance(item, dict):
            raise ADWikiError(f"{label} must be an object")
        allowed = {"id", "concept_id", "primary_source", "citation_depth", "conflict", "ambiguity"}
        _unknown_fields(item, allowed, label)
        if set(item) != allowed:
            raise ADWikiError(f"{label} has invalid required fields")
        depth = _text(item["citation_depth"], f"{label}.citation_depth")
        conflict = _text(item["conflict"], f"{label}.conflict")
        ambiguity = _text(item["ambiguity"], f"{label}.ambiguity")
        if depth not in CITATION_DEPTHS or conflict not in VISIBILITY or ambiguity not in VISIBILITY:
            raise ADWikiError(f"{label} has invalid evidence classification")
        claims.append(
            {
                "id": _text(item["id"], f"{label}.id"),
                "concept_id": _text(item["concept_id"], f"{label}.concept_id"),
                "primary_source": _bool(item["primary_source"], f"{label}.primary_source"),
                "citation_depth": depth,
                "conflict": conflict,
                "ambiguity": ambiguity,
            }
        )
    result["material_claims"] = claims
    _require_unique((item["id"] for item in claims), "material claim IDs")

    questions: list[dict[str, Any]] = []
    for index, item in enumerate(_list(value["representative_questions"], "representative_questions")):
        label = f"representative_questions[{index}]"
        if not isinstance(item, dict):
            raise ADWikiError(f"{label} must be an object")
        allowed = {
            "id",
            "outcome",
            "requires_descent",
            "descent_success",
            "asked_evidence_mode",
            "unrelated_source_access",
            "snapshot_disclosed",
            "wiki_assisted",
            "baseline",
            "user_feedback",
        }
        _unknown_fields(item, allowed, label)
        if set(item) != allowed:
            raise ADWikiError(f"{label} has invalid required fields")
        outcome = _text(item["outcome"], f"{label}.outcome")
        if outcome not in OUTCOMES:
            raise ADWikiError(f"{label}.outcome is invalid")
        requires_descent = _bool(item["requires_descent"], f"{label}.requires_descent")
        descent_success = item["descent_success"]
        if descent_success is not None:
            descent_success = _bool(descent_success, f"{label}.descent_success")
        if requires_descent and descent_success is None:
            raise ADWikiError(f"{label}.descent_success is required for a descent question")
        feedback = item["user_feedback"]
        if feedback is not None:
            if not isinstance(feedback, dict):
                raise ADWikiError(f"{label}.user_feedback must be an object or null")
            feedback_allowed = {"resolved", "actionable", "understood", "located_source", "needed_maintainer", "method"}
            _unknown_fields(feedback, feedback_allowed, f"{label}.user_feedback")
            if set(feedback) != feedback_allowed:
                raise ADWikiError(f"{label}.user_feedback has invalid required fields")
            feedback = {
                key: _bool(feedback[key], f"{label}.user_feedback.{key}")
                for key in ("resolved", "actionable", "understood", "located_source", "needed_maintainer")
            } | {"method": _text(feedback["method"], f"{label}.user_feedback.method")}
        questions.append(
            {
                "id": _text(item["id"], f"{label}.id"),
                "outcome": outcome,
                "requires_descent": requires_descent,
                "descent_success": descent_success,
                "asked_evidence_mode": _bool(item["asked_evidence_mode"], f"{label}.asked_evidence_mode"),
                "unrelated_source_access": _bool(item["unrelated_source_access"], f"{label}.unrelated_source_access"),
                "snapshot_disclosed": _bool(item["snapshot_disclosed"], f"{label}.snapshot_disclosed"),
                "wiki_assisted": _validate_journey(item["wiki_assisted"], f"{label}.wiki_assisted"),
                "baseline": _validate_journey(item["baseline"], f"{label}.baseline"),
                "user_feedback": feedback,
            }
        )
    result["representative_questions"] = questions
    _require_unique((item["id"] for item in questions), "representative question IDs")

    points: list[dict[str, int | float]] = []
    for index, item in enumerate(_list(value["scale_points"], "scale_points")):
        label = f"scale_points[{index}]"
        if not isinstance(item, dict):
            raise ADWikiError(f"{label} must be an object")
        _unknown_fields(item, {"repository_size", "wiki_size"}, label)
        if set(item) != {"repository_size", "wiki_size"}:
            raise ADWikiError(f"{label} has invalid required fields")
        points.append(
            {
                "repository_size": _integer(item["repository_size"], f"{label}.repository_size"),
                "wiki_size": _integer(item["wiki_size"], f"{label}.wiki_size"),
            }
        )
    result["scale_points"] = points
    return result


def _has_symlink_component(path: Path, root: Path) -> bool:
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _load_assessment(root: Path, relative_or_absolute: str | Path) -> dict[str, Any]:
    unresolved = Path(relative_or_absolute).expanduser()
    lexical = unresolved if unresolved.is_absolute() else root / unresolved
    try:
        lexical.relative_to(root)
    except ValueError as exc:
        raise ADWikiError("Wiki health assessment must be inside the AD-Wiki repository") from exc
    if _has_symlink_component(lexical, root):
        raise ADWikiError("Wiki health assessment must not use a symlink")
    path = lexical.resolve()
    if not _path_is_within(path, root) or not path.is_file():
        raise ADWikiError("Wiki health assessment must be a file inside the AD-Wiki repository")
    size = path.stat().st_size
    if size > MAX_ASSESSMENT_BYTES:
        raise ADWikiError(f"Wiki health assessment exceeds {MAX_ASSESSMENT_BYTES} bytes")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ADWikiError(f"Wiki health assessment must be UTF-8 JSON: {exc}") from exc
    return _validate_assessment(value)


def _git_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unborn"
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", revision) else "unborn"


def _metric(
    metric_id: str,
    *,
    calculated_at: str,
    value: int | float,
    numerator: int | float,
    denominator: int | float,
    status: str,
    evidence: list[dict[str, Any]],
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "scope": scope or {"kind": "wiki", "paths": []},
        "evidence": evidence,
        "calculated_at": calculated_at,
        "status": status,
        "unavailable_reason": None,
    }


def _ratio_metric(
    metric_id: str,
    numerator: int | float,
    denominator: int | float,
    *,
    calculated_at: str,
    pass_when: bool = True,
    evidence: list[dict[str, Any]],
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = 1.0 if denominator == 0 and numerator == 0 else numerator / denominator
    return _metric(
        metric_id,
        calculated_at=calculated_at,
        value=value,
        numerator=numerator,
        denominator=denominator,
        status="pass" if pass_when else "fail",
        evidence=evidence,
        scope=scope,
    )


def _unavailable(metric_id: str, reason: str, calculated_at: str, *, kind: str = "wiki") -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": None,
        "numerator": None,
        "denominator": None,
        "scope": {"kind": kind, "paths": []},
        "evidence": [{"kind": "missing-input", "reason": reason, "paths": []}],
        "calculated_at": calculated_at,
        "status": "unavailable",
        "unavailable_reason": reason,
    }


def _bundle_digest(bundle: Path) -> str:
    paths, unsafe = _bundle_markdown_files(bundle)
    if unsafe:
        raise ADWikiError("Wiki health cannot digest unsafe Bundle paths")
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(bundle).as_posix()):
        relative = path.relative_to(bundle).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _concept_records(root: Path, bundle: Path) -> list[dict[str, Any]]:
    paths, _ = _bundle_markdown_files(bundle)
    records: list[dict[str, Any]] = []
    for path in paths:
        if path.name in {"index.md", "log.md"}:
            continue
        parsed = _frontmatter(path.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        fields, _, _ = _top_level(parsed[0])
        records.append(
            {
                "path": path,
                "relative": path.relative_to(bundle).as_posix(),
                "repo_relative": path.relative_to(root).as_posix(),
                "concept_id": path.relative_to(bundle).with_suffix("").as_posix(),
                "fields": fields,
                "lines": parsed[0],
                "body": parsed[1],
                "sources": _source_entries(parsed[0], fields.get("sources")),
            }
        )
    return records


def _citation_facts(records: list[dict[str, Any]]) -> tuple[int, int]:
    total = 0
    valid = 0
    for record in records:
        source_ids = {item.get("id") for item in record["sources"] if item.get("id")}
        for line in record["body"].splitlines():
            if line.lstrip().startswith("[^"):
                continue
            for label in FOOTNOTE.findall(line):
                total += 1
                valid += label in source_ids
    return valid, total


def _managed_link_facts(records: list[dict[str, Any]], validation: dict[str, Any]) -> tuple[int, int, list[str]]:
    managed_paths = {
        record["repo_relative"]
        for record in records
        if MANAGED_START in record["body"] or record["relative"].startswith("implementations/")
    }
    total = sum(len(MARKDOWN_LINK.findall(record["body"])) for record in records if f"wiki/{record['relative']}" in managed_paths)
    issues = [
        item
        for item in [*validation["errors"], *validation["warnings"]]
        if item.get("code") in {"ADW-W210", "ADW-W211", "ADW-E120"} and item.get("path") in managed_paths
    ]
    return len(issues), total, sorted({str(item["path"]) for item in issues})


def _validate_assessment_references(root: Path, records: list[dict[str, Any]], assessment: dict[str, Any]) -> None:
    concept_ids = {record["concept_id"] for record in records}
    evidence_paths = [
        path
        for item in [*assessment["key_systems"], *assessment["canonical_terms"]]
        for path in item["evidence"]
    ]
    for relative in evidence_paths:
        lexical = root / relative
        if _has_symlink_component(lexical, root):
            raise ADWikiError(f"assessment evidence path must not use a symlink: {relative}")
        resolved = lexical.resolve()
        if not _path_is_within(resolved, root) or not resolved.is_file():
            raise ADWikiError(f"assessment evidence path does not exist: {relative}")
    referenced_ids = [
        concept_id
        for item in assessment["key_systems"]
        for concept_id in item["concept_ids"]
    ] + [item["concept_id"] for item in assessment["material_claims"]]
    unknown = sorted({concept_id for concept_id in referenced_ids if concept_id not in concept_ids})
    if unknown:
        raise ADWikiError(f"assessment references unknown Concept ID: {unknown[0]}")


def _assessment_metrics(assessment: dict[str, Any] | None, calculated_at: str) -> dict[str, dict[str, Any]]:
    ids = {
        "key-system-coverage",
        "toc-completeness",
        "glossary-coverage",
        "primary-source-coverage",
        "citation-depth",
        "conflict-visibility",
        "ambiguity-visibility",
        "representative-question-success",
        "evidence-descent-success",
        "path-compression-gain",
        "wiki-repository-scale-relationship",
        "user-usefulness",
        "snapshot-consistency",
        "silent-detected-conflicts",
    }
    if assessment is None:
        return {metric_id: _unavailable(metric_id, "semantic assessment was not supplied", calculated_at) for metric_id in ids}
    evidence = [{"kind": "assessment", "schema_version": "1", "paths": []}]
    result: dict[str, dict[str, Any]] = {}
    systems = assessment["key_systems"]
    represented = sum(bool(item["concept_ids"] and item["evidence"]) for item in systems)
    result["key-system-coverage"] = _ratio_metric(
        "key-system-coverage", represented, len(systems), calculated_at=calculated_at, evidence=evidence, pass_when=represented == len(systems)
    ) if systems else _unavailable("key-system-coverage", "assessment has no key systems", calculated_at)
    dimension_total = len(systems) * len(DIMENSIONS)
    dimension_true = sum(sum(item["dimensions"].values()) for item in systems)
    result["toc-completeness"] = _ratio_metric(
        "toc-completeness", dimension_true, dimension_total, calculated_at=calculated_at, evidence=evidence, pass_when=dimension_true == dimension_total
    ) if systems else _unavailable("toc-completeness", "assessment has no key systems", calculated_at)
    terms = assessment["canonical_terms"]
    covered_terms = sum(item["defined"] and item["consistent"] for item in terms)
    result["glossary-coverage"] = _ratio_metric(
        "glossary-coverage", covered_terms, len(terms), calculated_at=calculated_at, evidence=evidence, pass_when=covered_terms == len(terms)
    ) if terms else _unavailable("glossary-coverage", "assessment has no canonical terms", calculated_at)
    claims = assessment["material_claims"]
    if claims:
        primary = sum(item["primary_source"] for item in claims)
        deep = sum(item["citation_depth"] in {"section", "code"} for item in claims)
        conflicts = [item for item in claims if item["conflict"] != "none"]
        visible_conflicts = sum(item["conflict"] == "visible" for item in conflicts)
        ambiguities = [item for item in claims if item["ambiguity"] != "none"]
        visible_ambiguities = sum(item["ambiguity"] == "visible" for item in ambiguities)
        result["primary-source-coverage"] = _ratio_metric("primary-source-coverage", primary, len(claims), calculated_at=calculated_at, evidence=evidence, pass_when=primary == len(claims))
        result["citation-depth"] = _ratio_metric("citation-depth", deep, len(claims), calculated_at=calculated_at, evidence=evidence, pass_when=deep == len(claims))
        result["conflict-visibility"] = _ratio_metric("conflict-visibility", visible_conflicts, len(conflicts), calculated_at=calculated_at, evidence=evidence, pass_when=visible_conflicts == len(conflicts))
        result["ambiguity-visibility"] = _ratio_metric("ambiguity-visibility", visible_ambiguities, len(ambiguities), calculated_at=calculated_at, evidence=evidence, pass_when=visible_ambiguities == len(ambiguities))
    else:
        for metric_id in ("primary-source-coverage", "citation-depth", "conflict-visibility", "ambiguity-visibility"):
            result[metric_id] = _unavailable(metric_id, "assessment has no material claims", calculated_at)

    snapshot_ok = assessment["snapshot_consistent"]
    result["snapshot-consistency"] = _metric(
        "snapshot-consistency", calculated_at=calculated_at, value=1 if snapshot_ok else 0, numerator=1 if snapshot_ok else 0, denominator=1, status="pass" if snapshot_ok else "fail", evidence=evidence
    )
    silent = sum(item["conflict"] == "silent" for item in claims)
    declared = assessment["detected_conflicts"]
    silent = max(silent, declared - sum(item["conflict"] == "visible" for item in claims))
    result["silent-detected-conflicts"] = _metric(
        "silent-detected-conflicts", calculated_at=calculated_at, value=silent, numerator=silent, denominator=declared, status="pass" if silent == 0 else "fail", evidence=evidence
    )

    questions = assessment["representative_questions"]
    if questions:
        successes = sum(item["outcome"] in {"compiled-hit", "source-descent", "knowledge-gap"} for item in questions)
        result["representative-question-success"] = _ratio_metric("representative-question-success", successes, len(questions), calculated_at=calculated_at, evidence=evidence, pass_when=successes == len(questions))
        descent = [item for item in questions if item["requires_descent"]]
        descent_success = sum(
            bool(item["descent_success"])
            and not item["asked_evidence_mode"]
            and not item["unrelated_source_access"]
            and item["snapshot_disclosed"]
            for item in descent
        )
        result["evidence-descent-success"] = _ratio_metric("evidence-descent-success", descent_success, len(descent), calculated_at=calculated_at, evidence=evidence, pass_when=descent_success == len(descent)) if descent else _unavailable("evidence-descent-success", "assessment has no Primary Source descent questions", calculated_at)
        gains: list[float] = []
        for item in questions:
            for key in ("steps", "files", "input_tokens", "time_ms", "wrong_turns"):
                baseline = item["baseline"][key]
                current = item["wiki_assisted"][key]
                if baseline > 0:
                    gains.append((baseline - current) / baseline)
        average = sum(gains) / len(gains) if gains else 0.0
        result["path-compression-gain"] = _metric("path-compression-gain", calculated_at=calculated_at, value=average, numerator=sum(gains), denominator=len(gains), status="pass" if average >= 0 else "warning", evidence=evidence) if gains else _unavailable("path-compression-gain", "assessment has no comparable non-zero baselines", calculated_at)
        feedback = [item["user_feedback"] for item in questions if item["user_feedback"] is not None]
        positive = sum(item["resolved"] and item["actionable"] for item in feedback)
        result["user-usefulness"] = _ratio_metric("user-usefulness", positive, len(feedback), calculated_at=calculated_at, evidence=evidence, pass_when=positive == len(feedback)) if feedback else _unavailable("user-usefulness", "assessment has no explicit or voluntary feedback", calculated_at)
    else:
        for metric_id in ("representative-question-success", "evidence-descent-success", "path-compression-gain", "user-usefulness"):
            result[metric_id] = _unavailable(metric_id, "assessment has no representative questions", calculated_at)

    points = assessment["scale_points"]
    if len(points) >= 2:
        x = [float(item["repository_size"]) for item in points]
        y = [float(item["wiki_size"]) for item in points]
        x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
        covariance = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True))
        variance = math.sqrt(sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y))
        correlation = covariance / variance if variance else 0.0
        result["wiki-repository-scale-relationship"] = _metric("wiki-repository-scale-relationship", calculated_at=calculated_at, value=correlation, numerator=covariance, denominator=variance, status="pass" if correlation > 0 else "warning", evidence=evidence)
    else:
        result["wiki-repository-scale-relationship"] = _unavailable("wiki-repository-scale-relationship", "assessment needs at least two comparable scale points", calculated_at)
    return result


def _latest_validated_code_source(root: Path) -> dict[str, Any] | None:
    runs = root / ".ad-wiki/runs"
    if not runs.is_dir() or runs.is_symlink():
        return None
    candidates: list[tuple[str, str, dict[str, Any]]] = []
    for path in runs.glob("*/run.json"):
        if (
            path.is_symlink()
            or _has_symlink_component(path, runs)
            or not _path_is_within(path.resolve(), runs)
            or not path.is_file()
            or path.stat().st_size > MAX_ASSESSMENT_BYTES
        ):
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or value.get("operation") != "code-wiki" or value.get("status") not in {"VALIDATED", "REVIEWED"}:
            continue
        code_wiki = value.get("code_wiki")
        source = code_wiki.get("code_source") if isinstance(code_wiki, dict) else None
        if isinstance(source, dict) and re.fullmatch(r"[0-9a-f]{40}", str(source.get("revision", ""))):
            candidates.append((str(value.get("updated_at", "")), path.parent.name, source))
    return max(candidates, default=("", "", None))[-1]


def _code_metrics(root: Path, bundle: Path, records: list[dict[str, Any]], code_repo: str | Path | None, calculated_at: str) -> tuple[dict[str, dict[str, Any]], int, list[str], str | None, bool]:
    ids = {"code-wiki-concept-evaluation", "invalid-code-references", "active-code-coverage"}
    code_root: Path | None = None
    if code_repo is not None:
        code_root = Path(code_repo).expanduser().resolve()
        source = inspect_code_repository(code_root)
    else:
        source = _latest_validated_code_source(root)
    if source is None:
        return ({metric_id: _unavailable(metric_id, "no code repository or validated Code Wiki run was found", calculated_at, kind="code") for metric_id in ids}, 0, [], None, False)
    cache = cache_root_for(root, source)
    try:
        graph, manifest = load_current_index(cache)
        bindings = load_bindings(cache)
    except ADWikiError as exc:
        reason = f"matching structural index is unavailable: {exc}"
        return ({metric_id: _unavailable(metric_id, reason, calculated_at, kind="code") for metric_id in ids}, 0, [], source["revision"], True)
    if bindings is None or bindings.get("revision") != source["revision"] or manifest.get("revision") != source["revision"] or bindings.get("graph_sha256") != manifest.get("graph_sha256"):
        reason = "matching structural bindings are unavailable"
        return ({metric_id: _unavailable(metric_id, reason, calculated_at, kind="code") for metric_id in ids}, 0, [], source["revision"], True)
    evidence = [{"kind": "code-index", "revision": source["revision"], "paths": []}]
    base_ids = {record["concept_id"] for record in records if not record["relative"].startswith(("implementations/", "sources/"))}
    binding_concepts = bindings["concepts"]
    evaluated = sum(
        concept_id in binding_concepts and binding_concepts[concept_id].get("status") not in {None, "pending"}
        for concept_id in base_ids
    )
    metrics: dict[str, dict[str, Any]] = {
        "code-wiki-concept-evaluation": _ratio_metric("code-wiki-concept-evaluation", evaluated, len(base_ids), calculated_at=calculated_at, evidence=evidence, pass_when=evaluated == len(base_ids), scope={"kind": "code", "paths": []})
    }
    nodes = {item["id"]: item for item in graph["nodes"]}
    all_symbols = [symbol for value in binding_concepts.values() for symbol in value.get("symbol_ids", [])]
    invalid = sorted({symbol for symbol in all_symbols if symbol not in nodes})
    metrics["invalid-code-references"] = _metric("invalid-code-references", calculated_at=calculated_at, value=len(invalid), numerator=len(invalid), denominator=len(set(all_symbols)), status="pass" if not invalid else "fail", evidence=evidence, scope={"kind": "code", "paths": []})
    supported = set(manifest.get("files", {}))
    touches: Counter[str] = Counter()
    if code_root is not None:
        try:
            history = subprocess.run(
                ["git", "log", "-n", "200", "--name-only", "--pretty=format:"],
                cwd=code_root,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            metrics["active-code-coverage"] = _unavailable("active-code-coverage", f"Git history is unavailable: {exc}", calculated_at, kind="code")
            return metrics, 0, invalid, source["revision"], True
        if history.returncode != 0:
            metrics["active-code-coverage"] = _unavailable("active-code-coverage", "Git history inspection failed", calculated_at, kind="code")
            return metrics, 0, invalid, source["revision"], True
        touches.update(line.strip() for line in history.stdout.splitlines() if line.strip() in supported)
    if not touches:
        touches.update({path: 1 for path in supported})
    bound_paths = {nodes[symbol]["source_file"] for symbol in all_symbols if symbol in nodes}
    total_weight = sum(touches.values())
    bound_weight = sum(weight for path, weight in touches.items() if path in bound_paths)
    metrics["active-code-coverage"] = _ratio_metric("active-code-coverage", bound_weight, total_weight, calculated_at=calculated_at, evidence=evidence, pass_when=bound_weight == total_weight, scope={"kind": "code", "paths": []}) if total_weight else _unavailable("active-code-coverage", "structural index has no supported files", calculated_at, kind="code")
    degree = Counter()
    for edge in graph["edges"]:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    bound_symbols = set(all_symbols)
    threshold = max(degree.values(), default=0)
    high_unbound = sorted(node_id for node_id, value in degree.items() if value == threshold and value > 0 and node_id not in bound_symbols)
    return metrics, len(high_unbound), invalid, source["revision"], True


def validate_health_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_top = {
        "schema_version",
        "plugin_version",
        "calculated_at",
        "repository",
        "assessment_identity",
        "overall_status",
        "metrics",
        "findings",
        "limits",
    }
    if set(report) != expected_top:
        errors.append("health report has invalid top-level fields")
    if report.get("schema_version") != HEALTH_SCHEMA_VERSION:
        errors.append("invalid health report schema_version")
    if report.get("overall_status") not in {"healthy", "unhealthy", "incomplete"}:
        errors.append("invalid overall_status")
    if "overall_score" in report:
        errors.append("health report must not contain overall_score")
    identity = report.get("assessment_identity")
    if not isinstance(identity, dict) or set(identity) != {"wiki_revision", "wiki_digest", "code_revision"}:
        errors.append("assessment_identity has invalid fields")
    elif (
        (identity["wiki_revision"] != "unborn" and not re.fullmatch(r"[0-9a-f]{40}", str(identity["wiki_revision"])))
        or not re.fullmatch(r"[0-9a-f]{64}", str(identity["wiki_digest"]))
        or (identity["code_revision"] is not None and not re.fullmatch(r"[0-9a-f]{40}", str(identity["code_revision"])))
    ):
        errors.append("assessment_identity is invalid")
    metrics = report.get("metrics")
    if not isinstance(metrics, list):
        return [*errors, "metrics must be a list"]
    ids = [item.get("metric_id") for item in metrics if isinstance(item, dict)]
    if ids != sorted(METRIC_IDS):
        errors.append("metrics must contain every metric exactly once in sorted order")
    required = {"metric_id", "value", "numerator", "denominator", "scope", "evidence", "calculated_at", "status", "unavailable_reason"}
    for item in metrics:
        if not isinstance(item, dict) or set(item) != required:
            errors.append("metric has invalid fields")
            continue
        if item["status"] not in {"pass", "warning", "fail", "unavailable"}:
            errors.append(f"metric {item['metric_id']} has invalid status")
        scope = item.get("scope")
        if not isinstance(scope, dict) or set(scope) != {"kind", "paths"} or not isinstance(scope.get("kind"), str) or not isinstance(scope.get("paths"), list):
            errors.append("metric scope has invalid fields")
        else:
            for path_value in scope["paths"]:
                path = PurePosixPath(str(path_value).replace("\\", "/"))
                if not isinstance(path_value, str) or path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", path_value):
                    errors.append("metric scope paths must be repository-relative")
                    break
        if not isinstance(item.get("evidence"), list) or any(not isinstance(entry, dict) for entry in item.get("evidence", [])):
            errors.append(f"metric {item['metric_id']} has invalid evidence")
        for key in ("value", "numerator", "denominator"):
            number = item.get(key)
            if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number)):
                errors.append(f"metric {item['metric_id']} has invalid {key}")
        if item["status"] == "unavailable":
            if any(item[key] is not None for key in ("value", "numerator", "denominator")) or not item["unavailable_reason"]:
                errors.append(f"metric {item['metric_id']} has invalid unavailable semantics")
        elif item["unavailable_reason"] is not None or not item["evidence"]:
            errors.append(f"metric {item['metric_id']} lacks available evidence")
    return errors


def inspect_wiki_health(
    repo: str | Path,
    *,
    assessment_path: str | Path | None = None,
    code_repo: str | Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    root = _repository_root(repo)
    _, bundle, _ = _configured_roots(root)
    calculated_at = _utc_now()
    current_date = today or date.today()
    assessment = _load_assessment(root, assessment_path) if assessment_path is not None else None
    wiki_revision = _git_revision(root)
    wiki_digest = _bundle_digest(bundle)
    if assessment is not None and assessment["wiki_revision"] != wiki_revision:
        raise ADWikiError("Wiki health assessment wiki_revision does not match the current Wiki")
    if assessment is not None and assessment["wiki_digest"] != wiki_digest:
        raise ADWikiError("Wiki health assessment wiki_digest does not match the current Wiki")
    validation = validate_repository(root, current_date)
    raw = guard_raw(root)
    records = _concept_records(root, bundle)
    if assessment is not None:
        _validate_assessment_references(root, records, assessment)
    metrics: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    registry_count = len(_load_registry(root)["sources"])
    valid_sources = max(0, registry_count - len(raw["violations"]))
    metrics["source-integrity"] = _ratio_metric("source-integrity", valid_sources, registry_count, calculated_at=calculated_at, evidence=[{"kind": "raw-guard", "checked": raw["checked"], "paths": []}], pass_when=raw["ok"], scope={"kind": "wiki", "paths": [".ad-wiki/source-registry.json"]}) if registry_count else _unavailable("source-integrity", "source registry is empty", calculated_at)
    valid_citations, citation_total = _citation_facts(records)
    metrics["citation-validity"] = _ratio_metric("citation-validity", valid_citations, citation_total, calculated_at=calculated_at, evidence=[{"kind": "bundle-validation", "paths": []}], pass_when=valid_citations == citation_total) if citation_total else _unavailable("citation-validity", "Wiki has no material claim citations", calculated_at)
    broken, managed_total, broken_paths = _managed_link_facts(records, validation)
    metrics["broken-managed-links"] = _metric("broken-managed-links", calculated_at=calculated_at, value=broken, numerator=broken, denominator=managed_total, status="pass" if broken == 0 else "fail", evidence=[{"kind": "bundle-validation", "codes": ["ADW-W210", "ADW-W211", "ADW-E120"], "paths": broken_paths}])

    assessment_metrics = _assessment_metrics(assessment, calculated_at)
    metrics.update(assessment_metrics)
    stale = [item for item in [*validation["errors"], *validation["warnings"]] if item.get("code") == "ADW-W201"]
    orphan = [item for item in [*validation["errors"], *validation["warnings"]] if item.get("code") == "ADW-W240"]
    drift = [item for item in [*validation["errors"], *validation["warnings"]] if item.get("code") == "ADW-W230"]
    metrics["stale-rate"] = _ratio_metric("stale-rate", len(stale), len(records), calculated_at=calculated_at, evidence=[{"kind": "bundle-validation", "code": "ADW-W201", "paths": sorted({item["path"] for item in stale})}], pass_when=not stale)
    metrics["orphan-rate"] = _ratio_metric("orphan-rate", len(orphan), len(records), calculated_at=calculated_at, evidence=[{"kind": "bundle-validation", "code": "ADW-W240", "paths": sorted({item["path"] for item in orphan})}], pass_when=not orphan)
    metrics["index-drift"] = _metric("index-drift", calculated_at=calculated_at, value=len(drift), numerator=len(drift), denominator=max(1, len({record["path"].parent for record in records})), status="pass" if not drift else "warning", evidence=[{"kind": "bundle-validation", "code": "ADW-W230", "paths": sorted({item["path"] for item in drift})}])
    summary_resources = {
        item.get("resource")
        for record in records
        if record["fields"].get("type") == "Source Summary"
        for item in record["sources"]
        if item.get("resource")
    }
    concept_resources = {
        item.get("resource")
        for record in records
        if record["fields"].get("type") != "Source Summary"
        for item in record["sources"]
        if item.get("resource")
    }
    integrated = len(summary_resources & concept_resources)
    metrics["source-to-concept-yield"] = _ratio_metric("source-to-concept-yield", integrated, len(summary_resources), calculated_at=calculated_at, evidence=[{"kind": "bundle-provenance", "paths": []}], pass_when=integrated == len(summary_resources)) if summary_resources else _unavailable("source-to-concept-yield", "Wiki has no Source Summary resources", calculated_at)

    code_metrics, high_unbound, invalid_symbols, code_revision, code_applicable = _code_metrics(root, bundle, records, code_repo, calculated_at)
    metrics.update(code_metrics)
    if assessment is not None and code_applicable and assessment["code_revision"] != code_revision:
        raise ADWikiError("Wiki health assessment code_revision does not match the current code repository")
    revision_match = assessment is not None and assessment["wiki_revision"] == wiki_revision and (assessment["code_revision"] is None or assessment["code_revision"] == code_revision)
    metrics["source-code-snapshot-freshness"] = _metric("source-code-snapshot-freshness", calculated_at=calculated_at, value=1 if revision_match else 0, numerator=1 if revision_match else 0, denominator=1, status="pass" if revision_match else "warning", evidence=[{"kind": "revision-binding", "wiki_revision": wiki_revision, "code_revision": code_revision, "paths": []}]) if assessment is not None else _unavailable("source-code-snapshot-freshness", "semantic assessment was not supplied", calculated_at)
    semantic_risks = 0
    if assessment is not None:
        semantic_risks += sum(not (item["defined"] and item["consistent"]) for item in assessment["canonical_terms"])
        semantic_risks += sum(item["outcome"] in {"wrong-answer", "wrong-navigation"} for item in assessment["representative_questions"])
        semantic_risks += sum(not item["concept_ids"] for item in assessment["key_systems"])
    risk_count = semantic_risks + high_unbound
    risk_denominator = max(1, (len(assessment["canonical_terms"]) + len(assessment["representative_questions"]) + len(assessment["key_systems"]) if assessment else 0) + high_unbound)
    metrics["unknown-unknown-risk-signals"] = _metric("unknown-unknown-risk-signals", calculated_at=calculated_at, value=risk_count, numerator=risk_count, denominator=risk_denominator, status="pass" if risk_count == 0 else "warning", evidence=[{"kind": "risk-proxies", "high_centrality_unbound": high_unbound, "paths": []}]) if assessment is not None or code_repo is not None else _unavailable("unknown-unknown-risk-signals", "semantic assessment and code signals are unavailable", calculated_at)

    for violation in raw["violations"]:
        findings.append({"metric_id": "source-integrity", "code": violation["code"], "path": violation["path"]})
    for path in broken_paths:
        findings.append({"metric_id": "broken-managed-links", "code": "broken-managed-link", "path": path})
    if metrics["silent-detected-conflicts"]["status"] == "fail":
        findings.append({"metric_id": "silent-detected-conflicts", "code": "silent-conflict", "path": "assessment.json"})
    for symbol in invalid_symbols:
        findings.append({"metric_id": "invalid-code-references", "code": "invalid-symbol", "symbol_id": symbol})

    applicable_gates = set(ALWAYS_GATES)
    if assessment is not None:
        applicable_gates |= ASSESSMENT_GATES
    else:
        applicable_gates |= ASSESSMENT_GATES
    if code_applicable:
        applicable_gates |= CODE_GATES
    gate_metrics = [metrics[metric_id] for metric_id in applicable_gates]
    if any(item["status"] == "fail" for item in gate_metrics):
        overall = "unhealthy"
    elif any(item["status"] == "unavailable" for item in gate_metrics):
        overall = "incomplete"
    else:
        overall = "healthy"
    report = {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "calculated_at": calculated_at,
        "repository": ".",
        "assessment_identity": {
            "wiki_revision": wiki_revision,
            "wiki_digest": wiki_digest,
            "code_revision": code_revision,
        },
        "overall_status": overall,
        "metrics": [metrics[metric_id] for metric_id in sorted(METRIC_IDS)],
        "findings": sorted(findings, key=lambda item: (item["metric_id"], item.get("path", ""), item.get("symbol_id", ""))),
        "limits": [
            "Semantic and experiential metrics require an explicit version-bound assessment.",
            "Health inspection never fetches upstream sources, builds code indexes, executes code, or records Query text.",
        ],
    }
    errors = validate_health_report(report)
    if errors:
        raise ADWikiError("invalid Wiki health report: " + "; ".join(errors))
    return report
