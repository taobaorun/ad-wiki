from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.code_wiki import (  # noqa: E402
    checkpoint_code_wiki,
    finalize_code_wiki,
    prepare_code_wiki,
)
from ad_wiki.code_index.cache import cache_root_for, load_bindings, load_current_index  # noqa: E402
from ad_wiki.core import ADWikiError, build_indexes, initialize_repository  # noqa: E402
from ad_wiki.runtime import apply_run  # noqa: E402


def concept_text(title: str, *, type_name: str = "Concept", tags: str = "[framework]") -> str:
    coverage = "coverage: full\n" if type_name == "Source Summary" else ""
    return f"""---
type: {type_name}
title: {title}
description: {title} knowledge.
tags: {tags}
{coverage}status: draft
---

# {title}

Durable knowledge about {title}.
"""


class CodeWikiPrepareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        self.wiki = self.root / "wiki-repo"
        self.code = self.root / "code-repo"
        initialize_repository(self.wiki, "framework")
        self._write_wiki_fixture()
        self._init_code_repo(self.code)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str, cwd: Path | None = None, expected: int = 0) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.code,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return result.stdout.strip()

    def run_cli(self, script: str, *args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / script), *args, "--json"],
            cwd=PLUGIN_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def run_structural_cli(self, script: str, *args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "--project",
                str(PLUGIN_ROOT / "code-index"),
                "python",
                str(PLUGIN_ROOT / "scripts" / script),
                *args,
                "--json",
            ],
            cwd=PLUGIN_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def _init_code_repo(self, path: Path) -> None:
        path.mkdir(parents=True)
        self.git("init", "-b", "main", cwd=path)
        self.git("config", "user.name", "AD Wiki Test", cwd=path)
        self.git("config", "user.email", "ad-wiki@example.test", cwd=path)
        self.git("remote", "add", "origin", "https://example.test/framework.git", cwd=path)
        source = path / "src/Framework.java"
        source.parent.mkdir(parents=True)
        source.write_text("class Framework { void start() {} }\n")
        test = path / "src/test/FrameworkTest.java"
        test.parent.mkdir(parents=True)
        test.write_text("class FrameworkTest { void starts() {} }\n")
        generated = path / "target/Generated.java"
        generated.parent.mkdir(parents=True)
        generated.write_text("class Generated {}\n")
        self.git("add", ".", cwd=path)
        self.git("commit", "-m", "initial framework", cwd=path)

    def _write_wiki_fixture(self) -> None:
        pages = {
            "wiki/concepts/lifecycle.md": concept_text("Lifecycle"),
            "wiki/entities/framework.md": concept_text("Framework", type_name="Entity"),
            "wiki/sources/guide.md": concept_text("Guide", type_name="Source Summary"),
            "wiki/implementations/concepts/old.md": concept_text(
                "Old implementation", tags="[code-wiki, implementation]"
            ),
            "wiki/sources/code-framework-deadbeef.md": concept_text(
                "Old code snapshot",
                type_name="Source Summary",
                tags="[code-wiki-source]",
            ),
        }
        for relative, content in pages.items():
            path = self.wiki / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        build_indexes(self.wiki)

    def prepare(self, run_id: str = "code-wiki-framework") -> dict:
        return prepare_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)

    def staged(self, run_id: str, relative: str) -> Path:
        path = self.wiki / ".ad-wiki/runs" / run_id / "staged" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def stage_source_summary(self, result: dict, run_id: str) -> None:
        revision = result["code_wiki"]["code_source"]["revision"]
        self.staged(run_id, result["code_wiki"]["source_summary_path"]).write_text(
            f"""---
type: Source Summary
title: Framework code snapshot
description: Partial code snapshot inspected for Code Wiki enrichment.
tags: [code-wiki-source]
coverage: partial
status: draft
sources:
  - id: code-framework
    resource: https://example.test/framework
---

# Framework code snapshot

Revision `{revision}` code evidence.[^code-framework]

[^code-framework]: Framework repository revision.
"""
        )

    def stage_enriched(self, result: dict, run_id: str, concept_id: str) -> dict:
        concept = next(
            item for item in result["code_wiki"]["concepts"] if item["concept_id"] == concept_id
        )
        base_path = self.wiki / concept["path"]
        implementation_link = "/" + Path(concept["implementation_path"]).relative_to("wiki").as_posix()
        self.staged(run_id, concept["path"]).write_text(
            base_path.read_text()
            + "\n<!-- ad-code-wiki:start -->\n"
            + "## 实现原理\n\n"
            + f"- [查看源码实现]({implementation_link})\n"
            + "<!-- ad-code-wiki:end -->\n"
        )
        base_link = "/" + Path(concept["path"]).relative_to("wiki").as_posix()
        revision = result["code_wiki"]["code_source"]["revision"]
        self.staged(run_id, concept["implementation_path"]).write_text(
            f"""---
type: Concept
title: Lifecycle source implementation
description: Current implementation of lifecycle behavior.
tags: [code-wiki, implementation]
status: draft
sources:
  - id: code-framework
    resource: https://example.test/framework
---

# Lifecycle source implementation

[基础知识]({base_link})

## 代码快照

Revision `{revision}`；已读取 `src/Framework.java` 和测试源码。

## 对外契约

The public lifecycle starts the framework.[^code-framework]

## 实现原理

The current revision starts through `Framework#start`.[^code-framework]

## 运行流程

```mermaid
flowchart LR
    A["Framework"] --> B["start"]
```

## 核心代码

`src/Framework.java` — `Framework#start` — revision `{revision}`

```java
class Framework {{ void start() {{}} }}
```

## 关键符号与调用方

- `src/Framework.java#Framework#start` — starts the framework.

## 相关测试

本流程只阅读、未执行 `src/test/FrameworkTest.java#FrameworkTest#starts`。

## 文档与代码关系

实现补充。

## 不确定性与继续阅读

No additional callers were inspected.

[^code-framework]: `src/Framework.java`, `Framework#start`.
"""
        )
        return {
            "reason": "The Concept describes a runtime lifecycle mechanism.",
            "implementation_path": concept["implementation_path"],
            "code_refs": [
                {
                    "path": "src/Framework.java",
                    "symbol": "Framework#start",
                    "kind": "implementation",
                },
                {
                    "path": "src/test/FrameworkTest.java",
                    "symbol": "FrameworkTest#starts",
                    "kind": "test",
                },
            ],
            "feedback": [
                {
                    "kind": "implementation-only",
                    "summary": "The start call chain is absent from the public guide.",
                }
            ],
        }

    def checkpoint_remaining_docs_only(
        self,
        prepared: dict,
        run_id: str,
        *,
        exclude: set[str],
    ) -> None:
        for concept in prepared["code_wiki"]["concepts"]:
            if concept["concept_id"] in exclude:
                continue
            checkpoint_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id=run_id,
                concept_id=concept["concept_id"],
                status="docs-only",
                result={"reason": "No implementation page required."},
            )

    def test_prepares_stable_full_concept_inventory_and_git_identity(self) -> None:
        before_head = self.git("rev-parse", "HEAD")
        before_status = self.git("status", "--porcelain", "--untracked-files=all")

        result = prepare_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id="code-wiki-framework",
        )

        self.assertEqual(result["operation"], "code-wiki")
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["result"], "created")
        self.assertEqual(result["code_wiki"]["code_source"]["revision"], before_head)
        self.assertEqual(
            result["code_wiki"]["code_source"]["remote"],
            "https://example.test/framework",
        )
        concepts = result["code_wiki"]["concepts"]
        self.assertEqual(
            [item["concept_id"] for item in concepts],
            ["concepts/lifecycle", "entities/framework", "sources/guide"],
        )
        self.assertTrue(all(item["status"] == "pending" for item in concepts))
        self.assertEqual(result["code_wiki"]["coverage"]["inventory_total"], 3)
        self.assertEqual(result["code_wiki"]["coverage"]["pending"], 3)
        self.assertEqual(
            concepts[0]["implementation_path"],
            "wiki/implementations/concepts/lifecycle.md",
        )
        self.assertEqual(result["write_set"], [])
        self.assertTrue(
            (self.wiki / ".ad-wiki/runs/code-wiki-framework/staged").is_dir()
        )
        stored = json.loads(
            (self.wiki / ".ad-wiki/runs/code-wiki-framework/run.json").read_text()
        )
        self.assertEqual(stored["code_wiki"], result["code_wiki"])
        self.assertEqual(self.git("rev-parse", "HEAD"), before_head)
        self.assertEqual(
            self.git("status", "--porcelain", "--untracked-files=all"),
            before_status,
        )

        again = prepare_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id="code-wiki-framework",
        )
        self.assertEqual(again["result"], "unchanged")

        (self.wiki / "wiki/concepts/lifecycle.md").write_text(concept_text("Lifecycle changed"))
        with self.assertRaisesRegex(ADWikiError, "inventory or baseline changed"):
            prepare_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id="code-wiki-framework",
            )

    def test_accepts_clean_detached_head(self) -> None:
        revision = self.git("rev-parse", "HEAD")
        self.git("switch", "--detach", revision)

        result = prepare_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id="code-wiki-detached",
        )

        self.assertEqual(result["code_wiki"]["code_source"]["revision"], revision)

    def test_rejects_dirty_unborn_non_git_and_symlink_code_roots(self) -> None:
        (self.code / "untracked.txt").write_text("dirty\n")
        with self.assertRaisesRegex(ADWikiError, "clean Git worktree"):
            prepare_code_wiki(self.wiki, code_repo=self.code, run_id="dirty")
        self.assertFalse((self.wiki / ".ad-wiki/runs/dirty").exists())

        unborn = self.root / "unborn"
        unborn.mkdir()
        self.git("init", "-b", "main", cwd=unborn)
        with self.assertRaisesRegex(ADWikiError, "committed HEAD"):
            prepare_code_wiki(self.wiki, code_repo=unborn, run_id="unborn")

        plain = self.root / "plain"
        plain.mkdir()
        with self.assertRaisesRegex(ADWikiError, "Git worktree"):
            prepare_code_wiki(self.wiki, code_repo=plain, run_id="plain")

        link = self.root / "code-link"
        try:
            link.symlink_to(self.code, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "symlink"):
            prepare_code_wiki(self.wiki, code_repo=link, run_id="link")

    def test_checkpoints_all_concepts_finalizes_and_applies_atomically(self) -> None:
        run_id = "code-wiki-apply"
        prepared = self.prepare(run_id)
        self.stage_source_summary(prepared, run_id)
        enriched_result = self.stage_enriched(prepared, run_id, "concepts/lifecycle")

        first = checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="enriched",
            result=enriched_result,
        )
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="entities/framework",
            status="docs-only",
            result={"reason": "Entity identity has no separate implementation mechanism."},
        )
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="sources/guide",
            status="docs-only",
            result={"reason": "Source catalog page is documentation-only."},
        )

        self.assertEqual(first["code_wiki"]["coverage"]["evaluated"], 1)
        finalized = finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)
        self.assertTrue(finalized["code_wiki"]["finalized"])
        self.assertEqual(finalized["code_wiki"]["coverage"]["quality"], "complete")
        self.assertEqual(
            finalized["write_set"],
            sorted(
                [
                    "wiki/concepts/lifecycle.md",
                    "wiki/implementations/concepts/lifecycle.md",
                    prepared["code_wiki"]["source_summary_path"],
                ]
            ),
        )

        applied = apply_run(self.wiki, run_id=run_id)
        self.assertEqual(applied["status"], "VALIDATED")
        self.assertTrue((self.wiki / "wiki/implementations/concepts/lifecycle.md").is_file())
        self.assertIn("ad-code-wiki:start", (self.wiki / "wiki/concepts/lifecycle.md").read_text())
        self.assertIn(run_id, (self.wiki / "wiki/log.md").read_text())
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all"), "")

    def test_rejects_pending_finalize_and_unfinalized_apply(self) -> None:
        run_id = "code-wiki-pending"
        self.prepare(run_id)

        with self.assertRaisesRegex(ADWikiError, "not finalized"):
            apply_run(self.wiki, run_id=run_id)
        with self.assertRaisesRegex(ADWikiError, "pending"):
            finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)
        self.assertFalse((self.wiki / "wiki/implementations/concepts/lifecycle.md").exists())

    def test_checkpoint_is_idempotent_and_retry_is_explicit(self) -> None:
        run_id = "code-wiki-retry"
        self.prepare(run_id)
        initial = checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="needs-review",
            result={
                "reason": "Two implementation candidates remain.",
                "feedback": [
                    {"kind": "apparent-divergence", "summary": "Candidates differ."}
                ],
            },
        )
        unchanged = checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="needs-review",
            result={
                "reason": "Two implementation candidates remain.",
                "feedback": [
                    {"kind": "apparent-divergence", "summary": "Candidates differ."}
                ],
            },
        )
        self.assertEqual(initial["result"], "checkpointed")
        self.assertEqual(unchanged["result"], "unchanged")

        with self.assertRaisesRegex(ADWikiError, "--retry"):
            checkpoint_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id=run_id,
                concept_id="concepts/lifecycle",
                status="docs-only",
                result={"reason": "Reclassified after further inspection."},
            )
        retried = checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="docs-only",
            result={"reason": "Reclassified after further inspection."},
            retry=True,
        )
        self.assertEqual(retried["code_wiki"]["coverage"]["docs_only"], 1)
        self.assertTrue(any(event.get("event") == "code-wiki-retry" for event in retried["events"]))

    def test_retry_from_enriched_removes_obsolete_staged_pair(self) -> None:
        run_id = "code-wiki-retry-enriched"
        prepared = self.prepare(run_id)
        self.stage_source_summary(prepared, run_id)
        result = self.stage_enriched(prepared, run_id, "concepts/lifecycle")
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="enriched",
            result=result,
        )
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="docs-only",
            result={"reason": "Further inspection found no durable implementation layer."},
            retry=True,
        )
        self.checkpoint_remaining_docs_only(
            prepared,
            run_id,
            exclude={"concepts/lifecycle"},
        )

        finalized = finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)

        self.assertEqual(finalized["write_set"], [prepared["code_wiki"]["source_summary_path"]])
        self.assertFalse(
            self.staged(run_id, "wiki/implementations/concepts/lifecycle.md").exists()
        )

    def test_apply_rejects_post_finalize_tampering_and_rolls_back_invalid_bundle(self) -> None:
        run_id = "code-wiki-tamper"
        prepared = self.prepare(run_id)
        self.stage_source_summary(prepared, run_id)
        self.checkpoint_remaining_docs_only(prepared, run_id, exclude=set())
        finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)
        staged_source = self.staged(run_id, prepared["code_wiki"]["source_summary_path"])
        staged_source.write_text(staged_source.read_text() + "\ntampered\n")
        with self.assertRaisesRegex(ADWikiError, "changed after Finalize"):
            apply_run(self.wiki, run_id=run_id)

        run_id = "code-wiki-rollback"
        prepared = self.prepare(run_id)
        original_base = (self.wiki / "wiki/concepts/lifecycle.md").read_bytes()
        original_log = (self.wiki / "wiki/log.md").read_bytes()
        result = self.stage_enriched(prepared, run_id, "concepts/lifecycle")
        revision = prepared["code_wiki"]["code_source"]["revision"]
        self.staged(run_id, prepared["code_wiki"]["source_summary_path"]).write_text(
            f"""---
type: Source Summary
title: Invalid source summary
description: Invalid inline sources for rollback proof.
tags: [code-wiki-source]
coverage: partial
status: draft
sources: [invalid]
---

# Invalid source summary

Revision `{revision}`.
"""
        )
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="enriched",
            result=result,
        )
        self.checkpoint_remaining_docs_only(
            prepared,
            run_id,
            exclude={"concepts/lifecycle"},
        )
        finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)

        with self.assertRaisesRegex(ADWikiError, "post-apply Bundle validation failed"):
            apply_run(self.wiki, run_id=run_id)

        self.assertEqual((self.wiki / "wiki/concepts/lifecycle.md").read_bytes(), original_base)
        self.assertEqual((self.wiki / "wiki/log.md").read_bytes(), original_log)
        self.assertFalse((self.wiki / "wiki/implementations/concepts/lifecycle.md").exists())
        self.assertFalse((self.wiki / prepared["code_wiki"]["source_summary_path"]).exists())

    def test_finalize_rejects_unplanned_staged_files_and_wiki_drift(self) -> None:
        run_id = "code-wiki-extra"
        prepared = self.prepare(run_id)
        self.stage_source_summary(prepared, run_id)
        for concept in prepared["code_wiki"]["concepts"]:
            checkpoint_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id=run_id,
                concept_id=concept["concept_id"],
                status="docs-only",
                result={"reason": "No implementation page required."},
            )
        self.staged(run_id, "wiki/concepts/unplanned.md").write_text(concept_text("Unplanned"))
        with self.assertRaisesRegex(ADWikiError, "unplanned staged"):
            finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)

        run_id = "code-wiki-drift"
        prepared = self.prepare(run_id)
        self.stage_source_summary(prepared, run_id)
        for concept in prepared["code_wiki"]["concepts"]:
            checkpoint_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id=run_id,
                concept_id=concept["concept_id"],
                status="docs-only",
                result={"reason": "No implementation page required."},
            )
        (self.wiki / "wiki/concepts/lifecycle.md").write_text(concept_text("Changed"))
        with self.assertRaisesRegex(ADWikiError, "baseline drifted"):
            finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)

    def test_finalize_rejects_base_semantic_changes_and_suspected_secrets(self) -> None:
        run_id = "code-wiki-base-change"
        prepared = self.prepare(run_id)
        self.stage_source_summary(prepared, run_id)
        result = self.stage_enriched(prepared, run_id, "concepts/lifecycle")
        staged_base = self.staged(run_id, "wiki/concepts/lifecycle.md")
        staged_base.write_text(staged_base.read_text().replace("Lifecycle", "Changed Lifecycle"))
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="enriched",
            result=result,
        )
        self.checkpoint_remaining_docs_only(
            prepared,
            run_id,
            exclude={"concepts/lifecycle"},
        )
        with self.assertRaisesRegex(ADWikiError, "only change the managed link block"):
            finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)

        run_id = "code-wiki-secret"
        prepared = self.prepare(run_id)
        self.stage_source_summary(prepared, run_id)
        result = self.stage_enriched(prepared, run_id, "concepts/lifecycle")
        staged_impl = self.staged(run_id, "wiki/implementations/concepts/lifecycle.md")
        credential_line = '{} = "{}"\n'.format("pass" + "word", "super" + "secret")
        staged_impl.write_text(staged_impl.read_text() + "\n" + credential_line)
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="enriched",
            result=result,
        )
        self.checkpoint_remaining_docs_only(
            prepared,
            run_id,
            exclude={"concepts/lifecycle"},
        )
        with self.assertRaisesRegex(ADWikiError, "suspected secret"):
            finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)

    def test_checkpoint_rejects_generated_or_vendored_code_refs(self) -> None:
        run_id = "code-wiki-generated-ref"
        self.prepare(run_id)
        with self.assertRaisesRegex(ADWikiError, "generated, vendored, or sensitive"):
            checkpoint_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id=run_id,
                concept_id="concepts/lifecycle",
                status="needs-review",
                result={
                    "reason": "Only generated code matched.",
                    "code_refs": [
                        {
                            "path": "target/Generated.java",
                            "symbol": "Generated",
                            "kind": "implementation",
                        }
                    ],
                },
            )

    def test_cli_runs_prepare_checkpoint_finalize_and_apply(self) -> None:
        run_id = "code-wiki-cli"
        prepared = self.run_cli(
            "prepare_code_wiki.py",
            "--repo",
            str(self.wiki),
            "--code-repo",
            str(self.code),
            "--run-id",
            run_id,
        )
        self.stage_source_summary(prepared, run_id)
        enriched = self.stage_enriched(prepared, run_id, "concepts/lifecycle")
        self.run_cli(
            "checkpoint_code_wiki.py",
            "--repo",
            str(self.wiki),
            "--code-repo",
            str(self.code),
            "--run-id",
            run_id,
            "--concept",
            "concepts/lifecycle",
            "--status",
            "enriched",
            "--result-json",
            json.dumps(enriched),
        )
        for concept in prepared["code_wiki"]["concepts"]:
            if concept["concept_id"] == "concepts/lifecycle":
                continue
            self.run_cli(
                "checkpoint_code_wiki.py",
                "--repo",
                str(self.wiki),
                "--code-repo",
                str(self.code),
                "--run-id",
                run_id,
                "--concept",
                concept["concept_id"],
                "--status",
                "docs-only",
                "--result-json",
                json.dumps({"reason": "No implementation layer required."}),
            )
        finalized = self.run_cli(
            "finalize_code_wiki.py",
            "--repo",
            str(self.wiki),
            "--code-repo",
            str(self.code),
            "--run-id",
            run_id,
        )
        applied = self.run_cli(
            "apply_run.py",
            "--repo",
            str(self.wiki),
            "--run-id",
            run_id,
        )

        self.assertTrue(finalized["code_wiki"]["finalized"])
        self.assertEqual(applied["status"], "VALIDATED")
        self.assertIn(
            "/implementations/concepts/lifecycle.md",
            (self.wiki / "wiki/implementations/concepts/index.md").read_text(),
        )

    def test_structural_mode_binds_v2_refs_publishes_and_reuses_unchanged(self) -> None:
        run_id = "code-wiki-structural"
        prepared = prepare_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            structural_index=True,
        )
        structural = prepared["code_wiki"]["structural_index"]
        self.assertTrue(structural["enabled"])
        graph, manifest = load_current_index(cache_root_for(self.wiki, prepared["code_wiki"]["code_source"]))
        method = next(
            item
            for item in graph["nodes"]
            if item.get("kind") == "method" and item.get("name") == "start"
        )
        self.stage_source_summary(prepared, run_id)
        result = self.stage_enriched(prepared, run_id, "concepts/lifecycle")
        staged_impl = self.staged(run_id, "wiki/implementations/concepts/lifecycle.md")
        staged_impl.write_text(staged_impl.read_text() + f"\nStructural symbol: `{method['label']}`\n")
        result.update(
            {
                "query_tokens": [token for token in ("framework", "start") if token in graph["vocab"]],
                "matched_node_ids": [method["id"]],
                "code_refs": [
                    {
                        "path": method["source_file"],
                        "symbol": method["label"],
                        "kind": "implementation",
                        "symbol_id": method["id"],
                        "relation": "contains",
                        "evidence": "EXTRACTED",
                        "source_location": method["source_location"],
                    }
                ],
            }
        )
        checkpoint_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            concept_id="concepts/lifecycle",
            status="enriched",
            result=result,
        )
        for concept in prepared["code_wiki"]["concepts"]:
            if concept["concept_id"] == "concepts/lifecycle":
                continue
            checkpoint_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id=run_id,
                concept_id=concept["concept_id"],
                status="docs-only",
                result={
                    "reason": "No implementation layer required.",
                    "query_tokens": [],
                    "matched_node_ids": [],
                },
            )
        finalized = finalize_code_wiki(self.wiki, code_repo=self.code, run_id=run_id)
        self.assertEqual(finalized["code_wiki"]["structural_index"]["graph_sha256"], manifest["graph_sha256"])
        apply_run(self.wiki, run_id=run_id)
        published = self.run_cli(
            "publish_code_bindings.py",
            "--repo",
            str(self.wiki),
            "--run-id",
            run_id,
        )
        self.assertEqual(published["result"], "published")
        bindings = load_bindings(cache_root_for(self.wiki, prepared["code_wiki"]["code_source"]))
        self.assertIn(method["id"], bindings["concepts"]["concepts/lifecycle"]["symbol_ids"])

        next_run = prepare_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id="code-wiki-structural-next",
            structural_index=True,
        )
        self.assertEqual(next_run["code_wiki"]["coverage"]["pending"], 0)
        self.assertEqual(next_run["code_wiki"]["coverage"]["unchanged"], 3)

        (self.code / "src/Framework.java").write_text(
            "class Framework { void start() {} void stop() {} }\n"
        )
        self.git("add", "src/Framework.java")
        self.git("commit", "-m", "change framework implementation")
        changed_run = prepare_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id="code-wiki-structural-changed",
            structural_index=True,
        )
        self.assertEqual(changed_run["code_wiki"]["coverage"]["pending"], 1)
        self.assertEqual(changed_run["code_wiki"]["coverage"]["unchanged"], 2)
        pending_ids = [
            item["concept_id"]
            for item in changed_run["code_wiki"]["concepts"]
            if item["status"] == "pending"
        ]
        self.assertEqual(pending_ids, ["concepts/lifecycle"])

    def test_structural_checkpoint_rejects_unknown_symbol_binding(self) -> None:
        run_id = "code-wiki-structural-invalid"
        prepared = prepare_code_wiki(
            self.wiki,
            code_repo=self.code,
            run_id=run_id,
            structural_index=True,
        )
        self.stage_enriched(prepared, run_id, "concepts/lifecycle")
        with self.assertRaisesRegex(ADWikiError, "absent from graph"):
            checkpoint_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id=run_id,
                concept_id="concepts/lifecycle",
                status="enriched",
                result={
                    "reason": "Invalid structural binding.",
                    "implementation_path": "wiki/implementations/concepts/lifecycle.md",
                    "query_tokens": [],
                    "matched_node_ids": [],
                    "code_refs": [
                        {
                            "path": "src/Framework.java",
                            "symbol": "missing",
                            "kind": "implementation",
                            "symbol_id": "java:method:missing",
                            "relation": "calls",
                            "evidence": "EXTRACTED",
                            "source_location": {"start_line": 1, "end_line": 1},
                        }
                    ],
                },
            )

    def test_structural_mode_fails_closed_without_uv_while_model_only_still_works(self) -> None:
        with patch("ad_wiki.code_wiki.shutil.which", return_value=None):
            with self.assertRaisesRegex(ADWikiError, "requires uv"):
                prepare_code_wiki(
                    self.wiki,
                    code_repo=self.code,
                    run_id="structural-no-uv",
                    structural_index=True,
                )
            model_only = prepare_code_wiki(
                self.wiki,
                code_repo=self.code,
                run_id="model-only-no-uv",
            )
        self.assertIsNone(model_only["code_wiki"]["structural_index"])

    def test_structural_cli_build_query_impact_and_cache_is_git_ignored(self) -> None:
        self.git("init", "-b", "main", cwd=self.wiki)
        self.git("config", "user.name", "AD Wiki Test", cwd=self.wiki)
        self.git("config", "user.email", "ad-wiki@example.test", cwd=self.wiki)
        self.git("add", ".", cwd=self.wiki)
        self.git("commit", "-m", "initial wiki", cwd=self.wiki)

        built = self.run_structural_cli(
            "build_code_index.py",
            "--repo",
            str(self.wiki),
            "--code-repo",
            str(self.code),
        )
        query = self.run_structural_cli(
            "query_code_index.py",
            "--repo",
            str(self.wiki),
            "--code-repo",
            str(self.code),
            "--request-json",
            json.dumps({"mode": "search", "tokens": ["start"]}),
        )
        impact = self.run_structural_cli(
            "inspect_code_impact.py",
            "--repo",
            str(self.wiki),
            "--code-repo",
            str(self.code),
            "--path",
            "src/Framework.java",
        )

        self.assertTrue(built["graph_sha256"])
        self.assertTrue(query["nodes"])
        self.assertIn("src/Framework.java", impact["changed_paths"])
        self.assertEqual(self.git("status", "--short", cwd=self.wiki), "")


if __name__ == "__main__":
    unittest.main()
