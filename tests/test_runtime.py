from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.core import (  # noqa: E402
    ADWikiError,
    build_indexes,
    initialize_repository,
    register_source,
    validate_repository,
)
from ad_wiki.runtime import (  # noqa: E402
    apply_run,
    approve_run,
    build_query_context,
    migrate_repository,
    prepare_run,
    query_registered_raw,
    review_run,
    search_repository,
)


def concept_text(title: str = "Incremental Compilation") -> str:
    return f"""---
type: Concept
title: {title}
description: Durable compiled knowledge.
status: draft
sources:
  - id: source-a
    resource: urn:test:source-a
---

# {title}

Persistent Wiki knowledge compounds across questions.[^source-a]

[^source-a]: Test source.
"""


class RuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name).resolve()
        initialize_repository(self.repo, "research")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def register(self) -> Path:
        source = self.repo / "raw/inbox/source.md"
        source.write_text("Persistent Wiki knowledge compounds.\n")
        register_source(self.repo, source, "urn:test:source-a")
        return source

    def prepare(self, run_id: str, *, risk: str = "medium", target: str = "wiki/concepts/compilation.md") -> Path:
        source = self.repo / "raw/inbox/source.md"
        if not source.exists():
            self.register()
        prepare_run(
            self.repo,
            run_id=run_id,
            operation="ingest",
            risk=risk,
            inputs=["raw/inbox/source.md"],
            read_set=["wiki/index.md"],
            write_set=[target],
        )
        staged = self.repo / ".ad-wiki/runs" / run_id / "staged" / target
        staged.parent.mkdir(parents=True, exist_ok=True)
        return staged

    def report(self, run_id: str) -> dict:
        return json.loads((self.repo / ".ad-wiki/runs" / run_id / "run.json").read_text())


class TransactionTests(RuntimeTestCase):
    def test_applies_indexes_logs_validates_and_reviews_one_write_set(self) -> None:
        staged = self.prepare("run-success")
        staged.write_text(concept_text())

        approved = approve_run(self.repo, run_id="run-success", actor="human:alice")
        applied = apply_run(self.repo, run_id="run-success")
        reviewed = review_run(
            self.repo,
            run_id="run-success",
            actor="human:alice",
            decision="approved",
            note="Claims and source attribution reviewed.",
        )

        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(applied["status"], "VALIDATED")
        self.assertEqual(reviewed["status"], "REVIEWED")
        self.assertTrue((self.repo / "wiki/concepts/compilation.md").is_file())
        self.assertIn("/concepts/compilation.md", (self.repo / "wiki/concepts/index.md").read_text())
        self.assertIn("run-success", (self.repo / "wiki/log.md").read_text())
        self.assertFalse((self.repo / ".ad-wiki/lock").exists())
        self.assertTrue(validate_repository(self.repo, today=date.today())["ok"])

    def test_rolls_back_all_bundle_files_when_post_apply_validation_fails(self) -> None:
        staged = self.prepare("run-invalid", risk="low")
        staged.write_text("# Missing frontmatter\n")
        original_log = (self.repo / "wiki/log.md").read_bytes()
        original_index = (self.repo / "wiki/index.md").read_bytes()
        approve_run(self.repo, run_id="run-invalid")

        with self.assertRaisesRegex(ADWikiError, "post-apply Bundle validation failed"):
            apply_run(self.repo, run_id="run-invalid")

        self.assertFalse((self.repo / "wiki/concepts/compilation.md").exists())
        self.assertEqual((self.repo / "wiki/log.md").read_bytes(), original_log)
        self.assertEqual((self.repo / "wiki/index.md").read_bytes(), original_index)
        self.assertEqual(self.report("run-invalid")["status"], "FAILED")

    def test_rejects_baseline_drift_before_touching_planned_targets(self) -> None:
        staged = self.prepare("run-drift", risk="low")
        staged.write_text(concept_text())
        approve_run(self.repo, run_id="run-drift")
        with (self.repo / "wiki/index.md").open("a", encoding="utf-8") as handle:
            handle.write("\nexternal change\n")

        with self.assertRaisesRegex(ADWikiError, "baseline drifted"):
            apply_run(self.repo, run_id="run-drift")

        self.assertFalse((self.repo / "wiki/concepts/compilation.md").exists())
        self.assertEqual(self.report("run-drift")["status"], "FAILED")

    def test_binds_approval_to_staged_bytes_and_review_to_validated_bytes(self) -> None:
        staged = self.prepare("run-bound", risk="low")
        staged.write_text(concept_text())
        approve_run(self.repo, run_id="run-bound")
        staged.write_text(concept_text("Changed After Approval"))

        with self.assertRaisesRegex(ADWikiError, "changed after approval"):
            apply_run(self.repo, run_id="run-bound")
        self.assertEqual(self.report("run-bound")["status"], "AUTO_APPROVED")

        staged.write_text(concept_text())
        applied = apply_run(self.repo, run_id="run-bound")
        self.assertEqual(applied["status"], "VALIDATED")
        target = self.repo / "wiki/concepts/compilation.md"
        target.write_text(concept_text("Changed After Validation"))
        with self.assertRaisesRegex(ADWikiError, "baseline drifted"):
            review_run(
                self.repo,
                run_id="run-bound",
                actor="human:alice",
                decision="approved",
            )

    def test_binds_approval_and_review_to_repository_policy(self) -> None:
        staged = self.prepare("run-policy-bound", risk="medium")
        staged.write_text(concept_text())
        config_path = self.repo / "ad-wiki.yaml"
        original_config = config_path.read_text()
        config = json.loads(original_config)
        config["review"]["owners"] = ["human:bob"]
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")

        with self.assertRaisesRegex(ADWikiError, "baseline drifted"):
            approve_run(self.repo, run_id="run-policy-bound", actor="human:bob")

        config_path.write_text(original_config)
        approve_run(self.repo, run_id="run-policy-bound", actor="human:alice")
        apply_run(self.repo, run_id="run-policy-bound")
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        with self.assertRaisesRegex(ADWikiError, "baseline drifted"):
            review_run(
                self.repo,
                run_id="run-policy-bound",
                actor="human:bob",
                decision="approved",
            )

    def test_lock_contention_is_retryable_and_does_not_change_run_state(self) -> None:
        staged = self.prepare("run-lock", risk="low")
        staged.write_text(concept_text())
        approve_run(self.repo, run_id="run-lock")
        (self.repo / ".ad-wiki/lock").write_text("held\n")

        with self.assertRaisesRegex(ADWikiError, "another AD-Wiki writer"):
            apply_run(self.repo, run_id="run-lock")

        self.assertEqual(self.report("run-lock")["status"], "AUTO_APPROVED")
        self.assertFalse((self.repo / "wiki/concepts/compilation.md").exists())

    def test_requires_exact_staged_write_set_and_configured_owner(self) -> None:
        config_path = self.repo / "ad-wiki.yaml"
        config = json.loads(config_path.read_text())
        config["review"]["owners"] = ["human:alice"]
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        staged = self.prepare("run-owned", risk="high")
        staged.write_text(concept_text())
        extra = staged.parent / "extra.md"
        extra.write_text(concept_text("Extra"))

        with self.assertRaisesRegex(ADWikiError, "unplanned"):
            approve_run(self.repo, run_id="run-owned", actor="human:alice")
        extra.unlink()
        with self.assertRaisesRegex(ADWikiError, "explicit approval actor"):
            approve_run(self.repo, run_id="run-owned")
        with self.assertRaisesRegex(ADWikiError, "not a configured owner"):
            approve_run(self.repo, run_id="run-owned", actor="human:bob")
        self.assertEqual(
            approve_run(self.repo, run_id="run-owned", actor="human:alice")["status"],
            "APPROVED",
        )
        apply_run(self.repo, run_id="run-owned")
        self.assertEqual(
            review_run(
                self.repo,
                run_id="run-owned",
                actor="human:bob",
                decision="approved",
            )["status"],
            "REVIEWED",
        )

    def test_empty_owner_list_blocks_only_high_risk_approval(self) -> None:
        medium = self.prepare("run-medium-open", risk="medium")
        medium.write_text(concept_text())
        self.assertEqual(
            approve_run(self.repo, run_id="run-medium-open", actor="human:writer")["status"],
            "APPROVED",
        )

        high = self.prepare("run-high-ownerless", risk="high", target="wiki/concepts/high.md")
        high.write_text(concept_text("High Risk"))
        with self.assertRaisesRegex(ADWikiError, "review.owners"):
            approve_run(self.repo, run_id="run-high-ownerless")

    def test_owner_allowlist_does_not_restrict_medium_approval_or_review(self) -> None:
        config_path = self.repo / "ad-wiki.yaml"
        config = json.loads(config_path.read_text())
        config["review"]["owners"] = ["human:owner"]
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        staged = self.prepare("run-medium-reviewer", risk="medium")
        staged.write_text(concept_text())

        approve_run(self.repo, run_id="run-medium-reviewer", actor="human:writer")
        apply_run(self.repo, run_id="run-medium-reviewer")
        reviewed = review_run(
            self.repo,
            run_id="run-medium-reviewer",
            actor="human:reviewer",
            decision="approved",
        )

        self.assertEqual(reviewed["status"], "REVIEWED")

    def test_medium_approval_and_all_reviews_require_human_actors(self) -> None:
        staged = self.prepare("run-human-audit", risk="medium")
        staged.write_text(concept_text())
        with self.assertRaisesRegex(ADWikiError, "human:<id>"):
            approve_run(self.repo, run_id="run-human-audit", actor="process:ad-wiki")

        approve_run(self.repo, run_id="run-human-audit", actor="human:writer")
        apply_run(self.repo, run_id="run-human-audit")
        with self.assertRaisesRegex(ADWikiError, "human:<id>"):
            review_run(
                self.repo,
                run_id="run-human-audit",
                actor="process:ad-wiki",
                decision="approved",
            )

    def test_transaction_log_uses_configured_content_language(self) -> None:
        staged = self.prepare("run-zh-log", risk="low")
        staged.write_text(concept_text())
        approve_run(self.repo, run_id="run-zh-log")
        apply_run(self.repo, run_id="run-zh-log")

        log = (self.repo / "wiki/log.md").read_text()
        self.assertTrue(log.startswith("# 知识包更新日志"))
        self.assertIn("已应用 1 个计划知识文件", log)

    def test_transaction_log_matches_run_ids_exactly(self) -> None:
        longer = self.prepare(
            "run-log4j2",
            risk="low",
            target="wiki/concepts/log4j2.md",
        )
        longer.write_text(concept_text("Log4j2"))
        approve_run(self.repo, run_id="run-log4j2")
        apply_run(self.repo, run_id="run-log4j2")

        shorter = self.prepare(
            "run-log",
            risk="low",
            target="wiki/concepts/logging.md",
        )
        shorter.write_text(concept_text("Log"))
        approve_run(self.repo, run_id="run-log")
        applied = apply_run(self.repo, run_id="run-log")

        log = (self.repo / "wiki/log.md").read_text()
        self.assertEqual(applied["status"], "VALIDATED")
        self.assertEqual(log.count("`run-log4j2`"), 1)
        self.assertEqual(log.count("`run-log`"), 1)

    def test_english_repository_keeps_deterministic_indexes_and_log_in_english(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            initialize_repository(repo, "research", content_language="en")
            source = repo / "raw/inbox/source.md"
            source.write_text("English source.\n")
            register_source(repo, source, "urn:test:english")
            prepare_run(
                repo,
                run_id="run-en-log",
                operation="ingest",
                risk="low",
                inputs=["raw/inbox/source.md"],
                read_set=["wiki/index.md"],
                write_set=["wiki/concepts/english.md"],
            )
            staged = repo / ".ad-wiki/runs/run-en-log/staged/wiki/concepts/english.md"
            staged.parent.mkdir(parents=True)
            staged.write_text(concept_text("English"))

            approve_run(repo, run_id="run-en-log")
            apply_run(repo, run_id="run-en-log")

            self.assertIn("## Concepts", (repo / "wiki/concepts/index.md").read_text())
            log = (repo / "wiki/log.md").read_text()
            self.assertTrue(log.startswith("# Knowledge Bundle Update Log"))
            self.assertIn("applied 1 planned knowledge file(s)", log)

    def test_enforces_supervised_batch_limit_and_run_directory_boundary(self) -> None:
        first = self.register()
        second = self.repo / "raw/inbox/second.md"
        second.write_text("Second source.\n")
        register_source(self.repo, second, "urn:test:second")
        with self.assertRaisesRegex(ADWikiError, "max_batch_size"):
            prepare_run(
                self.repo,
                run_id="run-batch",
                operation="ingest",
                risk="low",
                inputs=[
                    first.relative_to(self.repo).as_posix(),
                    second.relative_to(self.repo).as_posix(),
                ],
                read_set=["wiki/index.md"],
                write_set=["wiki/concepts/batch.md"],
            )

        runs = self.repo / ".ad-wiki/runs"
        runs.rmdir()
        outside = self.repo / "outside-runs"
        outside.mkdir()
        try:
            runs.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "must not be a symlink"):
            prepare_run(
                self.repo,
                run_id="run-escape",
                operation="writeback",
                risk="low",
                inputs=[],
                read_set=["wiki/index.md"],
                write_set=["wiki/concepts/escape.md"],
            )

    def test_rejects_symlinked_run_identity_hidden_concepts_and_broad_migration_targets(self) -> None:
        preseeded = self.repo / ".ad-wiki/runs/run-preseeded/staged/wiki/concepts"
        preseeded.mkdir(parents=True)
        (preseeded / "seed.md").write_text(concept_text("Preseeded"))
        with self.assertRaisesRegex(ADWikiError, "not empty"):
            prepare_run(
                self.repo,
                run_id="run-preseeded",
                operation="writeback",
                risk="low",
                inputs=[],
                read_set=["wiki/index.md"],
                write_set=["wiki/concepts/seed.md"],
            )

        outside = self.repo / "outside-run"
        outside.mkdir()
        run_directory = self.repo / ".ad-wiki/runs/run-symlink"
        try:
            run_directory.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "run directory"):
            prepare_run(
                self.repo,
                run_id="run-symlink",
                operation="writeback",
                risk="low",
                inputs=[],
                read_set=["wiki/index.md"],
                write_set=["wiki/concepts/safe.md"],
            )
        with self.assertRaisesRegex(ADWikiError, "hidden Bundle path"):
            prepare_run(
                self.repo,
                run_id="run-hidden",
                operation="writeback",
                risk="low",
                inputs=[],
                read_set=["wiki/index.md"],
                write_set=["wiki/.hidden/concept.md"],
            )
        with self.assertRaisesRegex(ADWikiError, "outside Profile state"):
            prepare_run(
                self.repo,
                run_id="run-migrate-code",
                operation="migrate",
                risk="high",
                inputs=[],
                read_set=["ad-wiki.yaml"],
                write_set=["unrelated.py"],
            )
        with self.assertRaisesRegex(ADWikiError, "immutable runtime state"):
            prepare_run(
                self.repo,
                run_id="run-migrate-registry",
                operation="migrate",
                risk="high",
                inputs=[],
                read_set=["ad-wiki.yaml"],
                write_set=[".ad-wiki/source-registry.json"],
            )


class SearchAndPolicyTests(RuntimeTestCase):
    def test_search_returns_ranked_concepts_and_sources_without_mutation(self) -> None:
        concept = self.repo / "wiki/concepts/compilation.md"
        concept.write_text(concept_text())
        build_indexes(self.repo)
        before = {
            path.relative_to(self.repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.repo.rglob("*")
            if path.is_file()
        }

        result = search_repository(self.repo, query="persistent compilation", limit=5)

        after = {
            path.relative_to(self.repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.repo.rglob("*")
            if path.is_file()
        }
        self.assertEqual(result["schema_version"], "2")
        self.assertEqual(result["mode"], "discovery")
        self.assertEqual(result["candidates"][0]["concept_id"], "concepts/compilation")
        self.assertEqual(result["candidates"][0]["sources"][0]["id"], "source-a")
        self.assertEqual(result["retrieval"]["algorithm_version"], "2")
        self.assertIn("persistent", result["candidates"][0]["matched_terms"])
        self.assertIn("body", result["candidates"][0]["matched_fields"])
        self.assertGreater(result["candidates"][0]["term_coverage"], 0)
        self.assertEqual(result["retrieval"]["candidate_count"], 1)
        self.assertEqual(result["retrieval"]["returned_count"], 1)
        self.assertNotIn("content", result["candidates"][0])
        self.assertEqual(before, after)

    def test_search_uses_chinese_phrases_instead_of_common_single_characters(self) -> None:
        target = self.repo / "wiki/concepts/extension-point.md"
        target.write_text(
            concept_text("SOFA 扩展点机制").replace(
                "Persistent Wiki knowledge compounds across questions.",
                "扩展点通过贡献点注册完成跨模块定制。",
            )
        )
        unrelated = self.repo / "wiki/concepts/application.md"
        unrelated.write_text(
            concept_text("SOFA 应用基础").replace(
                "Persistent Wiki knowledge compounds across questions.",
                "应用框架提供模块和服务能力。",
            )
        )
        build_indexes(self.repo)

        result = search_repository(
            self.repo,
            query="SOFA4 应用扩展点的原理是什么？如何使用扩展点？",
            limit=10,
        )

        self.assertEqual(result["candidates"][0]["concept_id"], "concepts/extension-point")
        self.assertIn("扩展点", result["candidates"][0]["matched_terms"])
        self.assertNotIn("的", result["candidates"][0]["matched_terms"])
        self.assertEqual(result["retrieval"]["candidate_count"], 1)

    def test_search_requires_more_than_generic_product_and_mechanism_terms(self) -> None:
        target = self.repo / "wiki/concepts/classloading.md"
        target.write_text(
            concept_text("SOFA4 类加载机制").replace(
                "Persistent Wiki knowledge compounds across questions.",
                "类加载使用独立 ClassLoader 完成模块隔离。",
            )
        )
        generic = self.repo / "wiki/concepts/generic.md"
        generic.write_text(
            concept_text("SOFA4 通用机制").replace(
                "Persistent Wiki knowledge compounds across questions.",
                "这是 SOFA4 的通用机制说明。",
            )
        )
        build_indexes(self.repo)

        result = search_repository(self.repo, query="SOFA4 的类加载机制如何工作？", limit=10)

        self.assertEqual(
            [item["concept_id"] for item in result["candidates"]],
            ["concepts/classloading"],
        )

    def test_search_ignores_english_question_framing(self) -> None:
        concept = self.repo / "wiki/concepts/persistence.md"
        concept.write_text(concept_text("Persistent Wiki"))
        build_indexes(self.repo)

        result = search_repository(self.repo, query="What is a persistent wiki?")

        self.assertEqual(
            [item["concept_id"] for item in result["candidates"]],
            ["concepts/persistence"],
        )
        self.assertEqual(result["candidates"][0]["matched_terms"], ["persistent", "wiki"])

    def test_search_ignores_chinese_question_framing_and_single_characters(self) -> None:
        concept = self.repo / "wiki/concepts/jvm-requirements.md"
        concept.write_text(concept_text("SOFA4 JVM 要求"))
        build_indexes(self.repo)

        result = search_repository(self.repo, query="SOFA4 对 JVM 有什么要求")

        self.assertEqual(
            [item["concept_id"] for item in result["candidates"]],
            ["concepts/jvm-requirements"],
        )
        self.assertEqual(result["candidates"][0]["matched_terms"], ["jvm", "sofa4", "要求"])

    def test_search_suppresses_source_summary_when_answer_concept_covers_resource(self) -> None:
        concept = self.repo / "wiki/concepts/extension-point.md"
        concept.write_text(concept_text("Extension Point"))
        summary = self.repo / "wiki/sources/extension-point.md"
        summary.write_text(concept_text("Extension Point Source").replace("type: Concept", "type: Source Summary"))
        build_indexes(self.repo)

        result = search_repository(self.repo, query="extension point", limit=10)

        self.assertEqual(
            [item["concept_id"] for item in result["candidates"]],
            ["concepts/extension-point"],
        )
        self.assertEqual(result["retrieval"]["suppressed_count"], 1)
        self.assertEqual(result["retrieval"]["candidate_count"], 1)

    def test_hydrates_explicit_concepts_in_caller_order_without_mutation(self) -> None:
        first = self.repo / "wiki/concepts/compilation.md"
        second = self.repo / "wiki/concepts/persistence.md"
        first.write_text(concept_text("Incremental Compilation"))
        second.write_text(concept_text("Persistent Wiki"))
        build_indexes(self.repo)
        before = {
            path.relative_to(self.repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.repo.rglob("*")
            if path.is_file()
        }

        envelope = build_query_context(
            self.repo,
            query="persistent wiki compilation",
            concept_ids=["concepts/persistence", "concepts/compilation", "concepts/persistence"],
            max_chars=30_000,
        )
        repeated = build_query_context(
            self.repo,
            query="persistent wiki compilation",
            concept_ids=["concepts/persistence", "concepts/compilation", "concepts/persistence"],
            max_chars=30_000,
        )

        after = {
            path.relative_to(self.repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.repo.rglob("*")
            if path.is_file()
        }
        self.assertEqual(envelope["schema_version"], "2")
        self.assertEqual(envelope["mode"], "hydration")
        self.assertEqual(envelope["repository"]["bundle"], "wiki")
        self.assertEqual(envelope["repository"]["content_language"], "zh-CN")
        self.assertEqual(envelope["repository"]["domain"], "research")
        self.assertEqual(envelope["repository"]["okf_version"], "0.2")
        self.assertEqual(envelope["repository"]["profile_version"], "0.1")
        self.assertEqual(envelope["hydration"]["selected_count"], 2)
        self.assertEqual(envelope["hydration"]["included_count"], 2)
        self.assertTrue(envelope["hydration"]["complete_pages"])
        self.assertEqual(envelope["concepts"][0]["concept_id"], "concepts/persistence")
        self.assertIn("# Persistent Wiki", envelope["concepts"][0]["content"])
        self.assertEqual(envelope["concepts"][1]["concept_id"], "concepts/compilation")
        self.assertFalse(Path(envelope["concepts"][0]["path"]).is_absolute())
        self.assertEqual(envelope, repeated)
        self.assertEqual(before, after)

    def test_discovery_score_does_not_choose_the_hydrated_knowledge_scope(self) -> None:
        focused = self.repo / "wiki/concepts/focused.md"
        focused.write_text(concept_text("Focused Answer"))
        supporting = self.repo / "wiki/concepts/supporting.md"
        supporting.write_text(
            concept_text("Supporting Note").replace(
                "Persistent Wiki knowledge compounds across questions.",
                "This page mentions focused and answer separately.",
            )
        )
        build_indexes(self.repo)

        discovery = search_repository(self.repo, query="focused answer")
        hydrated = build_query_context(
            self.repo,
            query="focused answer",
            concept_ids=["concepts/supporting"],
        )

        self.assertEqual(discovery["candidates"][0]["concept_id"], "concepts/focused")
        self.assertEqual(
            [item["concept_id"] for item in hydrated["concepts"]],
            ["concepts/supporting"],
        )
        self.assertNotIn("score", hydrated["concepts"][0])

    def test_hydration_enforces_atomic_character_and_selection_limits(self) -> None:
        (self.repo / "wiki/concepts/compilation.md").write_text(concept_text())
        (self.repo / "wiki/concepts/persistence.md").write_text(concept_text("Persistent Wiki"))
        build_indexes(self.repo)

        with self.assertRaisesRegex(ADWikiError, "exceeds max-chars"):
            build_query_context(
                self.repo,
                query="persistent wiki",
                concept_ids=["concepts/compilation"],
                max_chars=20,
            )

        many = []
        for index in range(9):
            concept_id = f"concepts/page-{index}"
            (self.repo / f"wiki/{concept_id}.md").write_text(concept_text(f"Page {index}"))
            many.append(concept_id)
        with self.assertRaisesRegex(ADWikiError, "at most 8 Concepts"):
            build_query_context(self.repo, query="pages", concept_ids=many)

    def test_query_context_rejects_out_of_range_limits(self) -> None:
        for value in (0, 1_000_001):
            with self.subTest(max_chars=value):
                with self.assertRaisesRegex(ADWikiError, "max-chars"):
                    build_query_context(
                        self.repo,
                        query="wiki",
                        concept_ids=["concepts/missing"],
                        max_chars=value,
                    )
        with self.assertRaisesRegex(ADWikiError, "at least one --concept"):
            build_query_context(self.repo, query="wiki", concept_ids=[])

    def test_hydration_rejects_hidden_reserved_and_symlinked_bundle_markdown(self) -> None:
        hidden = self.repo / "wiki/.private/secret.md"
        hidden.parent.mkdir()
        hidden.write_text(concept_text("Secret Wiki"))
        visible = self.repo / "wiki/concepts/visible.md"
        visible.write_text(concept_text("Visible Wiki"))
        build_indexes(self.repo)

        with self.assertRaisesRegex(ADWikiError, "invalid query hydration Concept ID"):
            build_query_context(
                self.repo,
                query="wiki",
                concept_ids=[".private/secret"],
            )
        with self.assertRaisesRegex(ADWikiError, "not a readable Bundle Concept"):
            build_query_context(self.repo, query="wiki", concept_ids=["index"])
        for aliased_id in ("concepts//visible", "concepts/./visible"):
            with self.subTest(concept_id=aliased_id):
                with self.assertRaisesRegex(ADWikiError, "invalid query hydration Concept ID"):
                    build_query_context(self.repo, query="wiki", concept_ids=[aliased_id])

        linked = self.repo / "wiki/concepts/linked.md"
        try:
            linked.symlink_to(visible)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "must not use a symlink"):
            build_query_context(self.repo, query="wiki", concept_ids=["concepts/linked"])

        envelope = build_query_context(
            self.repo,
            query="wiki",
            concept_ids=["concepts/visible"],
        )

        self.assertEqual(
            [item["concept_id"] for item in envelope["concepts"]],
            ["concepts/visible"],
        )

    def test_discovery_represents_no_matches_without_any_body_content(self) -> None:
        (self.repo / "wiki/concepts/compilation.md").write_text(concept_text())
        build_indexes(self.repo)

        catalog = search_repository(self.repo, query="unfindable-token")

        self.assertEqual(catalog["retrieval"]["candidate_count"], 0)
        self.assertEqual(catalog["retrieval"]["returned_count"], 0)
        self.assertEqual(catalog["candidates"], [])

    def test_query_protocol_refuses_an_explicitly_unsupported_okf_version(self) -> None:
        concept = self.repo / "wiki/concepts/compilation.md"
        concept.write_text(concept_text())
        (self.repo / "wiki/index.md").write_text('---\nokf_version: "9.9"\n---\n')

        with self.assertRaisesRegex(ADWikiError, "unsupported OKF version 9.9"):
            search_repository(self.repo, query="wiki")
        with self.assertRaisesRegex(ADWikiError, "unsupported OKF version 9.9"):
            build_query_context(
                self.repo,
                query="wiki",
                concept_ids=["concepts/compilation"],
            )

    def test_raw_fallback_reads_only_registered_sources_linked_by_selected_concepts(self) -> None:
        source = self.register()
        concept = self.repo / "wiki/concepts/compilation.md"
        concept.write_text(concept_text())
        other = self.repo / "raw/inbox/unrelated.md"
        other.write_text("unrelated-secret-token\n")
        register_source(self.repo, other, "urn:test:unrelated")
        build_indexes(self.repo)
        before = {
            path.relative_to(self.repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.repo.rglob("*")
            if path.is_file()
        }

        result = query_registered_raw(
            self.repo,
            query="persistent wiki",
            concept_ids=["concepts/compilation"],
            max_sources=2,
            max_chars=6_000,
        )
        unrelated = query_registered_raw(
            self.repo,
            query="unrelated-secret-token",
            concept_ids=["concepts/compilation"],
            max_sources=2,
            max_chars=6_000,
        )

        after = {
            path.relative_to(self.repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.repo.rglob("*")
            if path.is_file()
        }
        self.assertEqual(result["mode"], "raw-fallback")
        self.assertEqual(result["concepts"], ["concepts/compilation"])
        self.assertEqual(result["sources"][0]["path"], source.relative_to(self.repo).as_posix())
        self.assertEqual(result["sources"][0]["integrity"], "verified")
        self.assertIn("Persistent Wiki", result["sources"][0]["excerpts"][0]["content"])
        self.assertEqual(unrelated["sources"], [])
        self.assertEqual(unrelated["retrieval"]["linked_source_count"], 1)
        self.assertEqual(before, after)

    def test_raw_fallback_rejects_unregistered_or_changed_linked_sources(self) -> None:
        concept = self.repo / "wiki/concepts/unregistered.md"
        concept.write_text(concept_text().replace("urn:test:source-a", "urn:test:missing"))
        build_indexes(self.repo)
        with self.assertRaisesRegex(ADWikiError, "no registered Raw sources"):
            query_registered_raw(
                self.repo,
                query="persistent wiki",
                concept_ids=["concepts/unregistered"],
            )

        source = self.register()
        concept.write_text(concept_text())
        source.write_text("changed after registration\n")
        with self.assertRaisesRegex(ADWikiError, "registered Raw source changed"):
            query_registered_raw(
                self.repo,
                query="persistent wiki",
                concept_ids=["concepts/unregistered"],
            )

    def test_raw_fallback_does_not_validate_sources_beyond_the_source_budget(self) -> None:
        first = self.register()
        second = self.repo / "raw/inbox/second.md"
        second.write_text("Persistent Wiki second source.\n")
        register_source(self.repo, second, "urn:test:source-b")
        concept = self.repo / "wiki/concepts/bounded.md"
        concept.write_text(
            concept_text().replace(
                "    resource: urn:test:source-a",
                "    resource: urn:test:source-a\n"
                "  - id: source-b\n"
                "    resource: urn:test:source-b",
            )
        )
        second.write_text("changed outside the selected source budget\n")

        result = query_registered_raw(
            self.repo,
            query="persistent wiki",
            concept_ids=["concepts/bounded"],
            max_sources=1,
        )

        self.assertEqual(first.relative_to(self.repo).as_posix(), result["sources"][0]["path"])
        self.assertEqual(result["retrieval"]["linked_source_count"], 2)
        self.assertTrue(result["retrieval"]["source_limit_reached"])

    def test_raw_fallback_enforces_concept_and_budget_boundaries(self) -> None:
        self.register()
        concept = self.repo / "wiki/concepts/compilation.md"
        concept.write_text(concept_text())
        build_indexes(self.repo)

        with self.assertRaisesRegex(ADWikiError, "Concept ID"):
            query_registered_raw(self.repo, query="wiki", concept_ids=["../outside"])
        with self.assertRaisesRegex(ADWikiError, "max-sources"):
            query_registered_raw(self.repo, query="wiki", concept_ids=["concepts/compilation"], max_sources=0)
        with self.assertRaisesRegex(ADWikiError, "max-chars"):
            query_registered_raw(self.repo, query="wiki", concept_ids=["concepts/compilation"], max_chars=0)

        bounded = query_registered_raw(
            self.repo,
            query="persistent wiki",
            concept_ids=["concepts/compilation"],
            max_chars=12,
        )
        self.assertEqual(bounded["retrieval"]["included_chars"], 12)
        self.assertTrue(bounded["retrieval"]["content_truncated"])

    def test_raw_fallback_rejects_symlinked_concepts_and_sources(self) -> None:
        source = self.register()
        real_concept = self.repo / "wiki/concepts/real.md"
        real_concept.write_text(concept_text())
        linked_concept = self.repo / "wiki/concepts/linked.md"
        try:
            linked_concept.symlink_to(real_concept)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "Concept must not use a symlink"):
            query_registered_raw(self.repo, query="persistent wiki", concept_ids=["concepts/linked"])

        linked_concept.unlink()
        source_target = self.repo / "raw/inbox/source-target.md"
        source_target.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(source_target)
        with self.assertRaisesRegex(ADWikiError, "Raw source must not use a symlink"):
            query_registered_raw(self.repo, query="persistent wiki", concept_ids=["concepts/real"])

    def test_lint_policy_controls_severity_and_domain_types_are_visible(self) -> None:
        config_path = self.repo / "ad-wiki.yaml"
        config = json.loads(config_path.read_text())
        config["lint"].update(
            {
                "broken_links": "error",
                "orphan_pages": "ignore",
                "stale_content": "ignore",
            }
        )
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        concept = self.repo / "wiki/concepts/policy.md"
        concept.write_text(
            """---
type: Team Extension
title: Policy
stale_after: 2020-01-01
---

[Broken](/concepts/missing.md)
"""
        )
        build_indexes(self.repo)

        report = validate_repository(self.repo, today=date(2026, 8, 15))
        error_codes = {item["code"] for item in report["errors"]}
        warning_codes = {item["code"] for item in report["warnings"]}
        self.assertIn("ADW-E210", error_codes)
        self.assertIn("ADW-W250", warning_codes)
        self.assertNotIn("ADW-W201", warning_codes)
        self.assertNotIn("ADW-W240", warning_codes)

    def test_current_profile_migration_is_idempotent_and_unknown_target_is_refused(self) -> None:
        self.assertEqual(migrate_repository(self.repo)["status"], "current")
        with self.assertRaisesRegex(ADWikiError, "unsupported target profile"):
            migrate_repository(self.repo, target_profile="9.9")


class RepositoryIsolationTests(unittest.TestCase):
    def test_transaction_in_one_repository_leaves_another_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            repo_a = Path(first).resolve()
            repo_b = Path(second).resolve()
            initialize_repository(repo_a, "team-a")
            initialize_repository(repo_b, "team-b")
            source = repo_a / "raw/inbox/source.md"
            source.write_text("Team A only.\n")
            register_source(repo_a, source, "urn:test:team-a")
            before_b = {
                path.relative_to(repo_b).as_posix(): path.read_bytes()
                for path in repo_b.rglob("*")
                if path.is_file()
            }
            prepare_run(
                repo_a,
                run_id="run-team-a",
                operation="ingest",
                risk="low",
                inputs=["raw/inbox/source.md"],
                read_set=["wiki/index.md"],
                write_set=["wiki/concepts/team-a.md"],
            )
            staged = repo_a / ".ad-wiki/runs/run-team-a/staged/wiki/concepts/team-a.md"
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text(concept_text("Team A"))
            approve_run(repo_a, run_id="run-team-a")
            apply_run(repo_a, run_id="run-team-a")
            after_b = {
                path.relative_to(repo_b).as_posix(): path.read_bytes()
                for path in repo_b.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before_b, after_b)
            self.assertFalse((repo_b / "wiki/concepts/team-a.md").exists())


if __name__ == "__main__":
    unittest.main()
