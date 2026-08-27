from __future__ import annotations

import hashlib
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
CODE_WIKI_SKILL_ROOT = PLUGIN_ROOT / "skills/ad-code-wiki"
SHIP_SKILL_ROOT = PLUGIN_ROOT / "skills/ad-wiki-ship"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.core import PLUGIN_VERSION, STATIC_AGENT_FILES, validate_repository  # noqa: E402
from ad_wiki.doctor import inspect_plugin  # noqa: E402


class PackagingTests(unittest.TestCase):
    def test_dual_host_plugin_contracts_share_one_release_identity(self) -> None:
        codex = json.loads((PLUGIN_ROOT / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((PLUGIN_ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(PLUGIN_VERSION, "1.9.0")

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

    def test_plugin_root_is_flat_and_has_four_skills_with_one_runtime_core(self) -> None:
        self.assertFalse((PLUGIN_ROOT / "plugins").exists())
        self.assertTrue((PLUGIN_ROOT / "skills").is_dir())
        self.assertTrue((MAINTAINER_SKILL_ROOT / "SKILL.md").is_file())
        self.assertTrue((QUERY_SKILL_ROOT / "SKILL.md").is_file())
        self.assertTrue((CODE_WIKI_SKILL_ROOT / "SKILL.md").is_file())
        self.assertTrue((SHIP_SKILL_ROOT / "SKILL.md").is_file())
        self.assertEqual(
            list(PLUGIN_ROOT.rglob("skills/ad-wiki-maintainer/SKILL.md")),
            [MAINTAINER_SKILL_ROOT / "SKILL.md"],
        )
        self.assertEqual(
            list(PLUGIN_ROOT.rglob("skills/ad-wiki-query/SKILL.md")),
            [QUERY_SKILL_ROOT / "SKILL.md"],
        )
        self.assertEqual(
            list(PLUGIN_ROOT.rglob("skills/ad-code-wiki/SKILL.md")),
            [CODE_WIKI_SKILL_ROOT / "SKILL.md"],
        )
        self.assertEqual(
            list(PLUGIN_ROOT.rglob("skills/ad-wiki-ship/SKILL.md")),
            [SHIP_SKILL_ROOT / "SKILL.md"],
        )
        self.assertEqual(len(list(PLUGIN_ROOT.rglob("scripts/ad_wiki/core.py"))), 1)

    def test_maintainer_skill_owns_writes_but_not_public_query(self) -> None:
        skill = (MAINTAINER_SKILL_ROOT / "SKILL.md").read_text()
        self.assertNotIn("TODO", skill)
        self.assertIn("${CLAUDE_SKILL_DIR}", skill)
        self.assertIn("<plugin-root>/scripts/", skill)
        self.assertIn("content_language", skill)
        self.assertIn("whole long-lived Wiki", skill)
        self.assertIn("Do not create or update host memory", skill)
        self.assertNotIn("`../../scripts/", skill)
        for name in ("okf-profile.md", "workflows.md", "risk-policy.md", "migration-policy.md"):
            self.assertIn(f"references/{name}", skill)
            self.assertTrue((MAINTAINER_SKILL_ROOT / "references" / name).is_file())

        openai = (MAINTAINER_SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-wiki-maintainer", openai)
        self.assertIn("allow_implicit_invocation: true", openai)
        for command in (
            "prepare_run.py",
            "freeze_run.py",
            "apply_run.py",
            "review_run.py",
            "migrate_bundle.py",
        ):
            self.assertIn(command, skill)
        self.assertIn("--evidence-json", skill)
        self.assertIn("review_candidate.evidence_bindings", skill)
        self.assertIn("deprecated no-op shim", skill)
        self.assertNotIn("search_wiki.py", skill)
        self.assertNotIn("build_query_context.py", skill)
        self.assertNotIn("### Query", skill)

    def test_query_skill_owns_read_only_cited_answers(self) -> None:
        skill = (QUERY_SKILL_ROOT / "SKILL.md").read_text()
        description = skill.split("description: ", 1)[1].splitlines()[0]
        self.assertLessEqual(len(description), 240)
        self.assertIn("Always use", description)
        self.assertNotIn("TODO", skill)
        self.assertIn("<plugin-root>/scripts/query_registered_raw.py", skill)
        self.assertIn("references/query-contract.md", skill)
        self.assertIn("content_language", skill)
        self.assertIn("rg -n", skill)
        self.assertIn("Do not impose a fixed Top-K", skill)
        self.assertIn("Compiled hit", skill)
        self.assertIn("Bounded Raw fallback", skill)
        self.assertIn("Knowledge gap", skill)
        self.assertIn("Shell or script execution is optional", skill)
        self.assertIn("one ephemeral multi-turn candidate", skill)
        self.assertIn("at least medium risk", skill)
        self.assertIn("staged candidate only", skill)
        self.assertIn("Do not substitute model memory", skill)
        self.assertIn("Never emit an absolute local path", skill)
        self.assertIn("reuse the current evidence", skill)
        self.assertIn("--concept <concept-id>", skill)
        self.assertIn("manual bounded fallback", skill)
        self.assertIn("inspect only the relevant document or section", skill)
        self.assertIn("Do not scan the Raw directory", skill)
        self.assertIn("the Wiki is a compressed navigation", skill)
        self.assertIn("automatically read the exact upstream primary source", skill)
        self.assertIn("Do not ask the user to choose Wiki, Raw, code, or MCP evidence mode", skill)
        self.assertIn("<plugin-root>/scripts/resolve_code_worktree.py", skill)
        self.assertIn("bounded Raw fallback or exact local code resolution", skill)
        self.assertIn("require only the selected path's command", skill)
        self.assertIn("Never scan the workspace", skill)
        self.assertIn("does not record the binding itself", skill)
        self.assertIn("git show <revision>:<path>", skill)
        self.assertNotIn("search_wiki.py", skill)
        self.assertNotIn("build_query_context.py", skill)
        self.assertNotIn("Context Envelope", skill)
        for command in ("prepare_run.py", "approve_run.py", "apply_run.py", "review_run.py"):
            self.assertNotIn(f"<plugin-root>/scripts/{command}", skill)
        self.assertNotIn("ad-wiki-maintainer/SKILL.md", skill)

        contract = (QUERY_SKILL_ROOT / "references/query-contract.md").read_text()
        self.assertIn("Query Contract v5", contract)
        self.assertIn("progressive disclosure", contract)
        self.assertIn("No deterministic scorer", contract)
        self.assertIn("roughly one thousand pages", contract)
        self.assertIn("writeback candidate", contract)
        self.assertIn("content_language", contract)
        self.assertIn("query_registered_raw.py", contract)
        self.assertIn("resolve an exact Concept-declared locator", contract)
        self.assertIn("must not scan the Raw directory", contract)
        self.assertIn("Raw files, source code, and commits remain primary evidence", contract)
        self.assertIn("automatically consult the exact upstream primary source", contract)
        self.assertIn("Exact local code resolution", contract)
        self.assertIn("resolve_code_worktree.py", contract)
        self.assertIn("git-object", contract)
        self.assertIn("at most one ephemeral current candidate", contract)
        self.assertIn("separate `apply`", contract)

        static_contract = STATIC_AGENT_FILES["AGENTS.md"]
        self.assertIn("prefer the installed AD Wiki Query runtime", static_contract)
        self.assertIn("never scan the Raw directory", static_contract)
        self.assertIn("the Wiki is path compression", static_contract)
        self.assertIn("Never scan sibling/workspace repositories", static_contract)

        openai = (QUERY_SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-wiki-query", openai)
        self.assertIn("allow_implicit_invocation: true", openai)

    def test_code_wiki_skill_owns_full_inventory_enrichment(self) -> None:
        skill = (CODE_WIKI_SKILL_ROOT / "SKILL.md").read_text()
        self.assertNotIn("TODO", skill)
        self.assertIn("every base Concept automatically evaluated", skill.split("---", 2)[1])
        self.assertIn("prepare_code_wiki.py", skill)
        self.assertIn("bind_code_worktree.py", skill)
        self.assertIn("host-local binding", skill)
        self.assertIn("without scanning sibling directories", skill)
        self.assertIn("checkpoint_code_wiki.py", skill)
        self.assertIn("finalize_code_wiki.py", skill)
        self.assertIn("apply_run.py", skill)
        self.assertIn("--structural-index", skill)
        self.assertIn("query_code_index.py", skill)
        self.assertIn("publish_code_bindings.py", skill)
        self.assertIn("EXTRACTED | INFERRED | AMBIGUOUS", skill)
        self.assertIn("Do not repair semantic Wiki content inside this run", skill)
        self.assertIn("Mermaid", skill)
        self.assertIn("tests were read but not executed", skill)
        self.assertNotIn("Concept selector", skill)

        contract = (CODE_WIKI_SKILL_ROOT / "references/code-wiki-contract.md").read_text()
        self.assertIn("Evaluate every base Concept", contract)
        self.assertIn("no-code-match", contract)
        self.assertIn("wiki/implementations/<base-concept-id>.md", contract)
        self.assertIn("Do not claim coverage of the full repository", contract)

        for relative in (
            "assets/implementation.md",
            "assets/code-source-summary.md",
            "assets/zh-CN/implementation.md",
            "assets/zh-CN/code-source-summary.md",
        ):
            text = (CODE_WIKI_SKILL_ROOT / relative).read_text()
            self.assertIn("code-wiki", text)
            self.assertIn(f"ad-wiki/{PLUGIN_VERSION}", text)

        openai = (CODE_WIKI_SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-code-wiki", openai)
        self.assertIn("allow_implicit_invocation: true", openai)

        pyproject = (PLUGIN_ROOT / "code-index/pyproject.toml").read_text()
        self.assertIn('tree-sitter==0.25.2', pyproject)
        self.assertIn('tree-sitter-java==0.23.5', pyproject)
        self.assertNotIn("graphify", pyproject.lower())
        self.assertTrue((PLUGIN_ROOT / "code-index/uv.lock").is_file())
        runtime_text = "\n".join(
            path.read_text()
            for path in (PLUGIN_ROOT / "scripts/ad_wiki/code_index").glob("*.py")
        )
        self.assertNotIn("import graphify", runtime_text)

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
            if expected_type == "Source Summary":
                self.assertIn("coverage: full", text)
                self.assertIn("coverage: full", localized_text)

        for name, tag in {
            "key-system-inventory.md": "ad-wiki-key-system-inventory",
            "glossary.md": "ad-wiki-glossary",
        }.items():
            text = (templates / name).read_text()
            localized = (templates / "zh-CN" / name).read_text()
            for candidate in (text, localized):
                self.assertIn("type: Concept", candidate)
                self.assertIn(tag, candidate)
                self.assertIn(f"by: ad-wiki/{PLUGIN_VERSION}", candidate)
                self.assertIn("Primary Sources", candidate)

        assessment = json.loads(
            (MAINTAINER_SKILL_ROOT / "assets/wiki-health-assessment.json").read_text()
        )
        self.assertEqual(assessment["schema_version"], "1")
        self.assertNotIn("prompt", assessment)

    def test_team_usable_runtime_entrypoints_are_packaged(self) -> None:
        scripts = PLUGIN_ROOT / "scripts"
        for name in (
            "prepare_run.py",
            "approve_run.py",
            "apply_run.py",
            "freeze_run.py",
            "bind_code_worktree.py",
            "resolve_code_worktree.py",
            "rebuild_code_source_registry.py",
            "review_run.py",
            "prepare_code_wiki.py",
            "checkpoint_code_wiki.py",
            "finalize_code_wiki.py",
            "build_code_index.py",
            "query_code_index.py",
            "inspect_code_impact.py",
            "publish_code_bindings.py",
            "query_registered_raw.py",
            "inspect_wiki_health.py",
            "doctor_plugin.py",
            "migrate_bundle.py",
            "build_wiki_skill.py",
        ):
            self.assertTrue((scripts / name).is_file(), name)
        for removed in ("search_wiki.py", "build_query_context.py"):
            self.assertFalse((scripts / removed).exists(), removed)

    def test_ship_skill_owns_local_read_only_skill_delivery(self) -> None:
        skill = (SHIP_SKILL_ROOT / "SKILL.md").read_text()
        self.assertIn("build_wiki_skill.py", skill)
        self.assertIn("one standalone read-only Skill", skill)
        self.assertIn("ad-${wiki-name}", skill)
        self.assertIn("does not deploy", skill)
        self.assertIn("canonical templates", skill)
        self.assertIn("directory`, `zip`, or `both", skill)
        self.assertIn("archive SHA-256", skill)
        self.assertNotIn("Writeback", skill)

        openai = (SHIP_SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-wiki-ship", openai)
        self.assertIn("allow_implicit_invocation: true", openai)
        for relative in (
            "assets/delivered-skill/SKILL.md.tmpl",
            "assets/delivered-skill/openai.yaml.tmpl",
            "assets/delivered-skill/query-contract.md",
        ):
            self.assertTrue((SHIP_SKILL_ROOT / relative).is_file(), relative)

    def test_maintainer_requires_model_navigation_and_atomic_compilation(self) -> None:
        skill = (MAINTAINER_SKILL_ROOT / "SKILL.md").read_text()
        workflows = (MAINTAINER_SKILL_ROOT / "references/workflows.md").read_text()
        for text in (skill, workflows):
            self.assertIn("Source Summary", text)
            self.assertIn("coverage: partial", text)
            self.assertIn("rg", text)
            self.assertNotIn("build_query_context.py", text)
            self.assertNotIn("search_wiki.py", text)
            self.assertIn("inspect_wiki_health.py", text)
            self.assertIn("Glossary", text)
            self.assertIn("key-system", text)

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
        for relative, expected in STATIC_AGENT_FILES.items():
            self.assertEqual((example / relative).read_text(), expected)
        self.assertTrue((example / "wiki/index.md").is_file())
        self.assertTrue((example / ".ad-wiki/source-registry.json").is_file())
        registry = json.loads((example / ".ad-wiki/source-registry.json").read_text())
        record = registry["sources"][0]
        self.assertEqual(
            record["canonical_locator"],
            "https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f",
        )
        self.assertEqual(record["source_id"], "SRC-63AE6A1C7CB2")
        self.assertEqual(
            hashlib.sha256((example / record["path"]).read_bytes()).hexdigest(),
            record["sha256"],
        )
        summary = (example / "wiki/sources/llm-wiki.md").read_text()
        self.assertIn("coverage: partial", summary)
        self.assertIn("must not be treated as full coverage", summary)


if __name__ == "__main__":
    unittest.main()
