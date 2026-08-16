from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PLUGIN_ROOT / "skills/ad-wiki-maintainer"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.core import PLUGIN_VERSION, validate_repository  # noqa: E402


class PackagingTests(unittest.TestCase):
    def test_dual_host_plugin_contracts_share_one_release_identity(self) -> None:
        codex = json.loads((PLUGIN_ROOT / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((PLUGIN_ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(PLUGIN_VERSION, "0.3.0")

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

    def test_plugin_root_is_flat_and_has_one_maintainer_core(self) -> None:
        self.assertFalse((PLUGIN_ROOT / "plugins").exists())
        self.assertTrue((PLUGIN_ROOT / "skills").is_dir())
        self.assertTrue((SKILL_ROOT / "SKILL.md").is_file())
        self.assertEqual(
            list(PLUGIN_ROOT.rglob("skills/ad-wiki-maintainer/SKILL.md")),
            [SKILL_ROOT / "SKILL.md"],
        )
        self.assertEqual(len(list(PLUGIN_ROOT.rglob("scripts/ad_wiki/core.py"))), 1)

    def test_skill_has_no_placeholders_and_declares_progressive_resources(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.assertNotIn("TODO", skill)
        self.assertIn("${CLAUDE_SKILL_DIR}", skill)
        self.assertIn("<plugin-root>/scripts/", skill)
        self.assertNotIn("`../../scripts/", skill)
        for name in ("okf-profile.md", "workflows.md", "risk-policy.md", "migration-policy.md"):
            self.assertIn(f"references/{name}", skill)
            self.assertTrue((SKILL_ROOT / "references" / name).is_file())

        openai = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-wiki-maintainer", openai)
        self.assertIn("allow_implicit_invocation: true", openai)
        for command in (
            "prepare_run.py",
            "approve_run.py",
            "apply_run.py",
            "review_run.py",
            "search_wiki.py",
            "migrate_bundle.py",
        ):
            self.assertIn(command, skill)

    def test_required_templates_exist_and_are_okf_shaped(self) -> None:
        templates = SKILL_ROOT / "assets/templates"
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

    def test_team_usable_runtime_entrypoints_are_packaged(self) -> None:
        scripts = PLUGIN_ROOT / "scripts"
        for name in (
            "prepare_run.py",
            "approve_run.py",
            "apply_run.py",
            "review_run.py",
            "search_wiki.py",
            "migrate_bundle.py",
        ):
            self.assertTrue((scripts / name).is_file(), name)

    def test_minimal_example_bundle_validates(self) -> None:
        example = PLUGIN_ROOT / "examples/minimal-wiki"
        report = validate_repository(example, today=date(2026, 8, 15))
        self.assertTrue(report["ok"], report)
        self.assertTrue((example / "wiki/index.md").is_file())
        self.assertTrue((example / ".ad-wiki/source-registry.json").is_file())


if __name__ == "__main__":
    unittest.main()
