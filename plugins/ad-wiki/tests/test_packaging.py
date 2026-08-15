from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PLUGIN_ROOT / "skills/ad-wiki-maintainer"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.core import validate_repository  # noqa: E402


class PackagingTests(unittest.TestCase):
    def test_plugin_and_marketplace_contracts_are_team_scoped(self) -> None:
        plugin = json.loads((PLUGIN_ROOT / ".codex-plugin/plugin.json").read_text())
        marketplace = json.loads((PLUGIN_ROOT.parents[1] / ".agents/plugins/marketplace.json").read_text())

        self.assertEqual(plugin["name"], "ad-wiki")
        self.assertEqual(plugin["version"], "0.1.0")
        self.assertEqual(plugin["skills"], "./skills/")
        self.assertNotIn("mcpServers", plugin)
        self.assertNotIn("apps", plugin)
        self.assertNotIn("hooks", plugin)
        self.assertEqual(marketplace["name"], "ad-wiki-team")
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["source"]["path"], "./plugins/ad-wiki")
        self.assertEqual(entry["policy"], {"installation": "AVAILABLE", "authentication": "ON_INSTALL"})

    def test_skill_has_no_placeholders_and_declares_progressive_resources(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        self.assertNotIn("TODO", skill)
        for name in ("okf-profile.md", "workflows.md", "risk-policy.md", "migration-policy.md"):
            self.assertIn(f"references/{name}", skill)
            self.assertTrue((SKILL_ROOT / "references" / name).is_file())

        openai = (SKILL_ROOT / "agents/openai.yaml").read_text()
        self.assertIn("$ad-wiki-maintainer", openai)
        self.assertIn("allow_implicit_invocation: true", openai)

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
            self.assertNotIn("verified:", text, name)

    def test_minimal_example_bundle_validates(self) -> None:
        example = PLUGIN_ROOT / "examples/minimal-wiki"
        report = validate_repository(example, today=date(2026, 8, 15))
        self.assertTrue(report["ok"], report)
        self.assertTrue((example / "wiki/index.md").is_file())
        self.assertTrue((example / ".ad-wiki/source-registry.json").is_file())


if __name__ == "__main__":
    unittest.main()
