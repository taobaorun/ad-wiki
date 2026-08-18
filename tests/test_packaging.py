from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MAINTAINER_SKILL_ROOT = PLUGIN_ROOT / "skills/ad-wiki-maintainer"
QUERY_SKILL_ROOT = PLUGIN_ROOT / "skills/ad-wiki-query"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.core import PLUGIN_VERSION, validate_repository  # noqa: E402
from ad_wiki.doctor import inspect_plugin  # noqa: E402


class PackagingTests(unittest.TestCase):
    def test_dual_host_plugin_contracts_share_one_release_identity(self) -> None:
        codex = json.loads((PLUGIN_ROOT / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((PLUGIN_ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(PLUGIN_VERSION, "1.1.0")

        for manifest in (codex, claude):
            self.assertEqual(manifest["name"], "ad-wiki")
            self.assertEqual(manifest["version"], PLUGIN_VERSION)
            self.assertEqual(manifest["author"]["name"], "AD Wiki Team")
            self.assertEqual(manifest["skills"], "./skills/")
            for deferred in (
                "mcpServers",
                "apps",
                "hooks",
                "agents",
                "commands",
                "lspServers",
            ):
                self.assertNotIn(deferred, manifest)

        self.assertIn("interface", codex)
        self.assertNotIn("interface", claude)
        self.assertEqual(claude["displayName"], "AD Wiki")
        self.assertNotIn("+", codex["version"])
        self.assertNotIn("+", claude["version"])

    def test_dual_host_marketplaces_resolve_the_same_plugin_root(self) -> None:
        distribution_root = PLUGIN_ROOT
        codex = json.loads((distribution_root / ".agents/plugins/marketplace.json").read_text())
        claude = json.loads((distribution_root / ".claude-plugin/marketplace.json").read_text())

        self.assertEqual(codex["name"], "ad-wiki-team")
        self.assertEqual(claude["name"], "ad-wiki-team")
        self.assertEqual(len(codex["plugins"]), 1)
        self.assertEqual(len(claude["plugins"]), 1)

        codex_entry = codex["plugins"][0]
        claude_entry = claude["plugins"][0]
        self.assertEqual(codex_entry["name"], "ad-wiki")
        self.assertEqual(claude_entry["name"], "ad-wiki")
        self.assertEqual(codex_entry["source"]["path"], "./")
        self.assertEqual(claude_entry["source"], "./")
        self.assertEqual(
            codex_entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )
        self.assertNotIn("version", claude_entry)

        codex_root = (distribution_root / codex_entry["source"]["path"]).resolve()
        claude_root = (distribution_root / claude_entry["source"]).resolve()
        self.assertEqual(codex_root, PLUGIN_ROOT)
        self.assertEqual(claude_root, PLUGIN_ROOT)

    def test_plugin_root_is_flat_and_has_two_skills_with_one_runtime_core(self) -> None:
        self.assertFalse((PLUGIN_ROOT / "plugins").exists())
        self.assertTrue((PLUGIN_ROOT / "skills").is_dir())
        self.assertTrue((MAINTAINER_SKILL_ROOT / "SKILL.md").is_file())
        self.assertTrue((QUERY_SKILL_ROOT / "SKILL.md").is_file())
        self.assertEqual(
            list(PLUGIN_ROOT.rglob("skills/ad-wiki-maintainer/SKILL.md")),
            [MAINTAINER_SKILL_ROOT / "SKILL.md"],
        )
        self.assertEqual(
            list(PLUGIN_ROOT.rglob("skills/ad-wiki-query/SKILL.md")),
            [QUERY_SKILL_ROOT / "SKILL.md"],
        )
        self.assertEqual(len(list(PLUGIN_ROOT.rglob("scripts/ad_wiki/core.py"))), 1)

    def test_maintainer_skill_owns_writes_but_not_public_query(self) -> None:
        skill = (MAINTAINER_SKILL_ROOT / "SKILL.md").read_text()
        self.assertNotIn("TODO", skill)
        self.assertIn("${CLAUDE_SKILL_DIR}", skill)
        self.assertIn("<plugin-root>/scripts/", skill)
        self.assertIn("content_language", skill)
        self.assertIn("--owner human:<id>", skill)
        self.assertNotIn("`../../scripts/", skill)
        for name in ("okf-profile.md", "workflows.md", "risk-policy.md", "migration-policy.md"):
            self.assertIn(f"references/{name}", skill)
            self.assertTrue((MAINTAINER_SKILL_ROOT / "references" / name).is_file())

        openai = (MAINTAINER_SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-wiki-maintainer", openai)
        self.assertIn("allow_implicit_invocation: true", openai)
        for command in (
            "prepare_run.py",
            "approve_run.py",
            "apply_run.py",
            "review_run.py",
            "search_wiki.py",
            "build_query_context.py",
            "migrate_bundle.py",
        ):
            self.assertIn(command, skill)
        self.assertNotIn("### Query", skill)

    def test_query_skill_owns_read_only_cited_answers(self) -> None:
        skill = (QUERY_SKILL_ROOT / "SKILL.md").read_text()
        self.assertNotIn("TODO", skill)
        self.assertIn("<plugin-root>/scripts/search_wiki.py", skill)
        self.assertIn("<plugin-root>/scripts/build_query_context.py", skill)
        self.assertIn("<plugin-root>/scripts/query_registered_raw.py", skill)
        self.assertIn("references/query-contract.md", skill)
        self.assertIn("content_language", skill)
        self.assertIn("Compiled hit", skill)
        self.assertIn("Bounded Raw fallback", skill)
        self.assertIn("Knowledge gap", skill)
        self.assertIn("Never emit an absolute local path", skill)
        self.assertIn("reuse the current hydrated content", skill)
        self.assertIn("--concept <concept-id>", skill)
        self.assertIn("Do not apply a fixed score percentage", skill)
        self.assertIn("retrieval.has_more_candidates", skill)
        self.assertNotIn("--selection-mode", skill)
        for command in ("prepare_run.py", "approve_run.py", "apply_run.py", "review_run.py"):
            self.assertNotIn(f"<plugin-root>/scripts/{command}", skill)
        self.assertNotIn("ad-wiki-maintainer/SKILL.md", skill)

        contract = (QUERY_SKILL_ROOT / "references/query-contract.md").read_text()
        self.assertIn("Discovery Catalog v2", contract)
        self.assertIn("Hydration Envelope v2", contract)
        self.assertIn("writeback candidate", contract)
        self.assertIn("content_language", contract)
        self.assertIn("has_more_candidates", contract)
        self.assertIn("reruns Discovery once", contract)
        self.assertIn("complete_pages", contract)
        self.assertIn("fails atomically", contract)
        self.assertNotIn("selection_mode", contract)
        self.assertIn("query_registered_raw.py", contract)

        openai = (QUERY_SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-wiki-query", openai)
        self.assertIn("allow_implicit_invocation: true", openai)

    def test_required_templates_exist_and_are_okf_shaped(self) -> None:
        templates = MAINTAINER_SKILL_ROOT / "assets/templates"
        for name, expected_type in {
            "source-summary.md": "Source Summary",
            "concept.md": "Concept",
            "synthesis.md": "Synthesis",
            "open-question.md": "Open Question",
        }.items():
            text = (templates / name).read_text()
            self.assertTrue(text.startswith("---\n"), name)
            self.assertIn(f"type: {expected_type}", text, name)
            self.assertIn("status: draft", text, name)
            self.assertIn(f"by: ad-wiki/{PLUGIN_VERSION}", text, name)
            self.assertNotIn("verified:", text, name)
            localized = templates / "zh-CN" / name
            self.assertTrue(localized.is_file(), localized)
            localized_text = localized.read_text()
            self.assertIn(f"type: {expected_type}", localized_text, name)
            self.assertIn("status: draft", localized_text, name)
            self.assertIn(f"by: ad-wiki/{PLUGIN_VERSION}", localized_text, name)
            self.assertNotIn("verified:", localized_text, name)

    def test_team_usable_runtime_entrypoints_are_packaged(self) -> None:
        scripts = PLUGIN_ROOT / "scripts"
        for name in (
            "prepare_run.py",
            "approve_run.py",
            "apply_run.py",
            "review_run.py",
            "search_wiki.py",
            "build_query_context.py",
            "query_registered_raw.py",
            "doctor_plugin.py",
            "migrate_bundle.py",
        ):
            self.assertTrue((scripts / name).is_file(), name)

    def test_maintainer_requires_retrieval_ready_atomic_compilation(self) -> None:
        skill = (MAINTAINER_SKILL_ROOT / "SKILL.md").read_text()
        workflows = (MAINTAINER_SKILL_ROOT / "references/workflows.md").read_text()
        for text in (skill, workflows):
            self.assertIn("Source Summary", text)
            self.assertIn("atomic", text)
            self.assertIn("representative", text)
            self.assertIn("compilation debt", text)
        self.assertIn("build_query_context.py --repo", skill)
        self.assertIn("build_query_context.py --concept", workflows)

    def test_plugin_doctor_reports_package_readiness_without_claiming_installation(self) -> None:
        healthy = inspect_plugin(PLUGIN_ROOT, repo=PLUGIN_ROOT / "examples/minimal-wiki")
        self.assertTrue(healthy["ready"], healthy)
        self.assertEqual(healthy["status"], "ready")
        self.assertIn("does not prove host installation", healthy["limits"][0])
        self.assertTrue(healthy["repository"]["ok"])

        with tempfile.TemporaryDirectory() as directory:
            broken = inspect_plugin(directory)
        self.assertFalse(broken["ready"])
        self.assertTrue(any("missing" in error for error in broken["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "ad-wiki"
            shutil.copytree(
                PLUGIN_ROOT,
                copied,
                ignore=shutil.ignore_patterns(".git", ".ruff_cache", "__pycache__"),
            )
            (copied / "scripts/init_bundle.py").unlink()
            incomplete = inspect_plugin(copied)
        self.assertFalse(incomplete["ready"])
        self.assertIn("missing packaged command: init_bundle.py", incomplete["errors"])

    def test_minimal_example_bundle_validates(self) -> None:
        example = PLUGIN_ROOT / "examples/minimal-wiki"
        report = validate_repository(example, today=date(2026, 8, 15))
        self.assertTrue(report["ok"], report)
        self.assertEqual(json.loads((example / "ad-wiki.yaml").read_text())["content_language"], "en")
        self.assertTrue((example / "wiki/index.md").is_file())
        self.assertTrue((example / ".ad-wiki/source-registry.json").is_file())


if __name__ == "__main__":
    unittest.main()
