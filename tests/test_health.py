from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.code_index.cache import (  # noqa: E402
    build_or_update_index,
    cache_root_for,
    publish_bindings,
)
from ad_wiki.code_wiki import inspect_code_repository  # noqa: E402
from ad_wiki.core import (  # noqa: E402
    ADWikiError,
    build_indexes,
    initialize_repository,
    register_source,
)
from ad_wiki.health import inspect_wiki_health, validate_health_report  # noqa: E402


def concept_text() -> str:
    return """---
type: Concept
title: Health Checks
description: How readiness health checks work.
tags: [health, readiness]
status: draft
stale_after: 2027-01-01
sources:
  - id: source-a
    resource: urn:test:source-a
---

# Health Checks

Applications run readiness checks before accepting traffic.[^source-a]

[^source-a]: Registered primary source.
"""


def complete_assessment() -> dict:
    return {
        "schema_version": "1",
        "wiki_revision": "unborn",
        "wiki_digest": None,
        "code_revision": None,
        "key_systems": [
            {
                "id": "health-checks",
                "evidence": ["wiki/concepts/health.md"],
                "concept_ids": ["concepts/health"],
                "dimensions": {
                    "entry": True,
                    "boundary": True,
                    "mechanism": True,
                    "dependencies": True,
                    "primary_sources": True,
                    "cross_links": True,
                },
            }
        ],
        "canonical_terms": [
            {
                "term": "Readiness Check",
                "evidence": ["wiki/concepts/health.md"],
                "defined": True,
                "consistent": True,
                "aliases": ["readiness"],
            }
        ],
        "material_claims": [
            {
                "id": "claim-health-before-traffic",
                "concept_id": "concepts/health",
                "primary_source": True,
                "citation_depth": "section",
                "conflict": "none",
                "ambiguity": "none",
            }
        ],
        "snapshot_consistent": True,
        "detected_conflicts": 0,
        "representative_questions": [
            {
                "id": "health-flow",
                "outcome": "compiled-hit",
                "requires_descent": False,
                "descent_success": None,
                "asked_evidence_mode": False,
                "unrelated_source_access": False,
                "snapshot_disclosed": True,
                "wiki_assisted": {
                    "steps": 2,
                    "files": 2,
                    "input_tokens": 1000,
                    "time_ms": 500,
                    "wrong_turns": 0,
                },
                "baseline": {
                    "steps": 5,
                    "files": 8,
                    "input_tokens": 5000,
                    "time_ms": 2500,
                    "wrong_turns": 1,
                },
                "user_feedback": {
                    "resolved": True,
                    "actionable": True,
                    "understood": True,
                    "located_source": True,
                    "needed_maintainer": False,
                    "method": "explicit-task-acceptance",
                },
            },
            {
                "id": "custom-health",
                "outcome": "source-descent",
                "requires_descent": True,
                "descent_success": True,
                "asked_evidence_mode": False,
                "unrelated_source_access": False,
                "snapshot_disclosed": True,
                "wiki_assisted": {
                    "steps": 3,
                    "files": 3,
                    "input_tokens": 1800,
                    "time_ms": 800,
                    "wrong_turns": 0,
                },
                "baseline": {
                    "steps": 8,
                    "files": 12,
                    "input_tokens": 8000,
                    "time_ms": 4000,
                    "wrong_turns": 2,
                },
                "user_feedback": None,
            },
        ],
        "scale_points": [
            {"repository_size": 1000, "wiki_size": 10},
            {"repository_size": 2000, "wiki_size": 18},
        ],
        "feedback": [],
    }


class WikiHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name).resolve()
        initialize_repository(self.repo, "health")
        source = self.repo / "raw/inbox/source.md"
        source.write_text("Readiness checks run before traffic.\n")
        register_source(self.repo, source, "urn:test:source-a")
        concept = self.repo / "wiki/concepts/health.md"
        concept.write_text(concept_text())
        build_indexes(self.repo)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def snapshot(self, root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    def write_assessment(self, value: dict | None = None) -> Path:
        candidate = json.loads(json.dumps(value or complete_assessment()))
        candidate["wiki_digest"] = inspect_wiki_health(self.repo)["assessment_identity"]["wiki_digest"]
        path = self.repo / "assessment.json"
        path.write_text(json.dumps(candidate, indent=2) + "\n")
        return path

    def metric(self, report: dict, metric_id: str) -> dict:
        return next(item for item in report["metrics"] if item["metric_id"] == metric_id)

    def test_without_assessment_is_read_only_and_honestly_incomplete(self) -> None:
        before = self.snapshot(self.repo)

        report = inspect_wiki_health(self.repo, today=date(2026, 8, 22))

        self.assertEqual(report["schema_version"], "1")
        self.assertEqual(report["overall_status"], "incomplete")
        self.assertNotIn("overall_score", report)
        self.assertRegex(report["assessment_identity"]["wiki_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual([item["metric_id"] for item in report["metrics"]], sorted(item["metric_id"] for item in report["metrics"]))
        for item in report["metrics"]:
            self.assertEqual(
                set(item),
                {
                    "metric_id",
                    "value",
                    "numerator",
                    "denominator",
                    "scope",
                    "evidence",
                    "calculated_at",
                    "status",
                    "unavailable_reason",
                },
            )
        self.assertEqual(self.metric(report, "source-integrity")["status"], "pass")
        self.assertEqual(self.metric(report, "key-system-coverage")["status"], "unavailable")
        self.assertTrue(self.metric(report, "key-system-coverage")["unavailable_reason"])
        self.assertEqual(before, self.snapshot(self.repo))

    def test_complete_assessment_calculates_health_vector_without_query_text(self) -> None:
        assessment = self.write_assessment()

        report = inspect_wiki_health(
            self.repo,
            assessment_path=assessment.relative_to(self.repo),
            today=date(2026, 8, 22),
        )

        self.assertEqual(report["overall_status"], "healthy")
        self.assertEqual(self.metric(report, "key-system-coverage")["value"], 1.0)
        self.assertEqual(self.metric(report, "toc-completeness")["value"], 1.0)
        self.assertEqual(self.metric(report, "glossary-coverage")["value"], 1.0)
        self.assertEqual(self.metric(report, "representative-question-success")["numerator"], 2)
        self.assertEqual(self.metric(report, "evidence-descent-success")["value"], 1.0)
        self.assertGreater(self.metric(report, "path-compression-gain")["value"], 0)
        self.assertEqual(self.metric(report, "user-usefulness")["status"], "pass")
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("custom-health", serialized)
        self.assertNotIn("Readiness checks run before traffic", serialized)
        self.assertNotIn(str(self.repo), serialized)

    def test_silent_conflict_is_an_uncompensated_hard_failure(self) -> None:
        value = complete_assessment()
        value["detected_conflicts"] = 1
        value["material_claims"][0]["conflict"] = "silent"
        assessment = self.write_assessment(value)

        report = inspect_wiki_health(self.repo, assessment_path=assessment.relative_to(self.repo))

        self.assertEqual(report["overall_status"], "unhealthy")
        self.assertEqual(self.metric(report, "silent-detected-conflicts")["status"], "fail")
        self.assertTrue(report["findings"])

    def test_assessment_rejects_escape_symlink_unknown_fields_and_oversize(self) -> None:
        outside = self.repo.parent / f"{self.repo.name}-outside.json"
        outside.write_text(json.dumps(complete_assessment()))
        self.addCleanup(outside.unlink)
        with self.assertRaisesRegex(ADWikiError, "inside the AD-Wiki repository"):
            inspect_wiki_health(self.repo, assessment_path=outside)

        linked = self.repo / "linked.json"
        try:
            linked.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "symlink"):
            inspect_wiki_health(self.repo, assessment_path=linked)

        unknown = complete_assessment()
        unknown["prompt"] = "a persisted user question"
        with self.assertRaisesRegex(ADWikiError, "unknown field"):
            inspect_wiki_health(self.repo, assessment_path=self.write_assessment(unknown).relative_to(self.repo))

        feedback = complete_assessment()
        feedback["feedback"] = ["captured prompt text"]
        with self.assertRaisesRegex(ADWikiError, "feedback must be empty"):
            inspect_wiki_health(self.repo, assessment_path=self.write_assessment(feedback).relative_to(self.repo))

        fractional = complete_assessment()
        fractional["detected_conflicts"] = 1.5
        with self.assertRaisesRegex(ADWikiError, "detected_conflicts must be a non-negative integer"):
            inspect_wiki_health(
                self.repo,
                assessment_path=self.write_assessment(fractional).relative_to(self.repo),
            )

        duplicate = complete_assessment()
        duplicate["representative_questions"].append(
            json.loads(json.dumps(duplicate["representative_questions"][0]))
        )
        with self.assertRaisesRegex(ADWikiError, "representative question IDs must be unique"):
            inspect_wiki_health(
                self.repo,
                assessment_path=self.write_assessment(duplicate).relative_to(self.repo),
            )

        escaped_evidence = complete_assessment()
        escaped_evidence["key_systems"][0]["evidence"] = ["../outside.md"]
        with self.assertRaisesRegex(ADWikiError, "repository-relative"):
            inspect_wiki_health(
                self.repo,
                assessment_path=self.write_assessment(escaped_evidence).relative_to(self.repo),
            )

        missing_evidence = complete_assessment()
        missing_evidence["key_systems"][0]["evidence"] = ["wiki/concepts/missing.md"]
        with self.assertRaisesRegex(ADWikiError, "evidence path does not exist"):
            inspect_wiki_health(
                self.repo,
                assessment_path=self.write_assessment(missing_evidence).relative_to(self.repo),
            )

        missing_concept = complete_assessment()
        missing_concept["material_claims"][0]["concept_id"] = "concepts/missing"
        with self.assertRaisesRegex(ADWikiError, "unknown Concept ID"):
            inspect_wiki_health(
                self.repo,
                assessment_path=self.write_assessment(missing_concept).relative_to(self.repo),
            )

        oversized = self.repo / "oversized.json"
        oversized.write_bytes(b" " * (2 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ADWikiError, "exceeds 2097152 bytes"):
            inspect_wiki_health(self.repo, assessment_path=oversized.relative_to(self.repo))

    def test_assessment_revision_and_report_schema_are_fail_closed(self) -> None:
        value = complete_assessment()
        value["wiki_revision"] = "0" * 40
        with self.assertRaisesRegex(ADWikiError, "wiki_revision does not match"):
            inspect_wiki_health(
                self.repo,
                assessment_path=self.write_assessment(value).relative_to(self.repo),
            )

        report = inspect_wiki_health(self.repo)
        report["overall_score"] = 99
        self.assertIn("health report must not contain overall_score", validate_health_report(report))
        del report["metrics"][0]["denominator"]
        self.assertIn("metric has invalid fields", validate_health_report(report))

        unsafe = inspect_wiki_health(self.repo)
        unsafe["metrics"][0]["scope"]["paths"] = [str(self.repo)]
        self.assertIn("metric scope paths must be repository-relative", validate_health_report(unsafe))

    def test_assessment_digest_detects_wiki_drift_at_the_same_revision(self) -> None:
        assessment = self.write_assessment()
        concept = self.repo / "wiki/concepts/health.md"
        concept.write_text(concept.read_text() + "\nChanged after assessment.\n")

        with self.assertRaisesRegex(ADWikiError, "wiki_digest does not match"):
            inspect_wiki_health(self.repo, assessment_path=assessment.relative_to(self.repo))

    def test_health_ignores_symlinked_code_wiki_run_metadata(self) -> None:
        assessment = self.write_assessment()
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            (outside / "run.json").write_text(
                json.dumps(
                    {
                        "operation": "code-wiki",
                        "status": "VALIDATED",
                        "updated_at": "2099-01-01T00:00:00Z",
                        "code_wiki": {"code_source": {"revision": "0" * 40}},
                    }
                )
            )
            linked = self.repo / ".ad-wiki/runs/escape"
            try:
                linked.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")

            report = inspect_wiki_health(
                self.repo,
                assessment_path=assessment.relative_to(self.repo),
            )

            self.assertIsNone(report["assessment_identity"]["code_revision"])

    def test_managed_link_gate_uses_the_configured_bundle_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            initialize_repository(repo, "custom-bundle")
            (repo / "wiki").rename(repo / "knowledge")
            config = json.loads((repo / "ad-wiki.yaml").read_text())
            config["bundle_root"] = "knowledge"
            (repo / "ad-wiki.yaml").write_text(json.dumps(config, indent=2) + "\n")
            source = repo / "raw/inbox/source.md"
            source.write_text("Evidence.\n")
            register_source(repo, source, "urn:test:source")
            concept = repo / "knowledge/concepts/managed.md"
            concept.write_text(
                """---
type: Concept
title: Managed
sources:
  - id: source
    resource: urn:test:source
---

# Managed

Evidence.[^source]

<!-- ad-code-wiki:start -->
[Implementation](/implementations/missing.md)
<!-- ad-code-wiki:end -->

[^source]: Registered source.
"""
            )
            build_indexes(repo)

            report = inspect_wiki_health(repo)

            self.assertEqual(self.metric(report, "broken-managed-links")["status"], "fail")
            self.assertEqual(report["overall_status"], "unhealthy")

    def test_code_metrics_use_matching_existing_graph_and_bindings_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code = Path(directory).resolve()
            subprocess.run(["git", "init", "-q"], cwd=code, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=code, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=code, check=True)
            source = code / "Framework.java"
            source.write_text("package demo; public class Framework { public void start() {} }\n")
            subprocess.run(["git", "add", "Framework.java"], cwd=code, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=code, check=True)
            code_source = inspect_code_repository(code)
            cache = cache_root_for(self.repo, code_source)
            index = build_or_update_index(code, cache_root=cache, revision=code_source["revision"])
            graph_path = cache / index["manifest"]["graph_file"]
            graph = json.loads(graph_path.read_text())
            symbol = next(item for item in graph["nodes"] if item["kind"] == "type")
            publish_bindings(
                cache,
                {
                    "schema_version": "1",
                    "revision": code_source["revision"],
                    "graph_sha256": index["graph_sha256"],
                    "concepts": {
                        "concepts/health": {
                            "status": "enriched",
                            "symbol_ids": [symbol["id"]],
                        }
                    },
                },
            )
            assessment_value = complete_assessment()
            assessment_value["code_revision"] = code_source["revision"]
            assessment = self.write_assessment(assessment_value)
            before = self.snapshot(code)

            report = inspect_wiki_health(
                self.repo,
                assessment_path=assessment.relative_to(self.repo),
                code_repo=code,
            )

            self.assertEqual(self.metric(report, "code-wiki-concept-evaluation")["value"], 1.0)
            self.assertEqual(self.metric(report, "invalid-code-references")["value"], 0)
            self.assertEqual(self.metric(report, "active-code-coverage")["status"], "pass")
            self.assertEqual(before, self.snapshot(code))

            run_path = self.repo / ".ad-wiki/runs/code-health/run.json"
            run_path.parent.mkdir(parents=True)
            run_path.write_text(
                json.dumps(
                    {
                        "operation": "code-wiki",
                        "status": "VALIDATED",
                        "updated_at": "2026-08-22T00:00:00Z",
                        "code_wiki": {"code_source": code_source},
                    }
                )
                + "\n"
            )
            cached_report = inspect_wiki_health(
                self.repo,
                assessment_path=assessment.relative_to(self.repo),
            )
            self.assertEqual(
                self.metric(cached_report, "code-wiki-concept-evaluation")["status"],
                "pass",
            )
            self.assertEqual(cached_report["assessment_identity"]["code_revision"], code_source["revision"])


if __name__ == "__main__":
    unittest.main()
