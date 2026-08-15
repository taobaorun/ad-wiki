from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"


class CLILifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_cli(self, script: str, *args: str, expected: int = 0) -> dict:
        command = [sys.executable, str(SCRIPTS / script), *args, "--json"]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_complete_local_lifecycle(self) -> None:
        initialized = self.run_cli("init_bundle.py", "--repo", str(self.repo), "--domain", "research")
        self.assertEqual(initialized["status"], "created")

        source = self.repo / "raw/inbox/paper.md"
        source.write_text("paper contents\n")
        registered = self.run_cli(
            "register_source.py",
            "--repo",
            str(self.repo),
            "--source",
            str(source),
            "--canonical-locator",
            "https://example.test/paper",
            "--author",
            "human:alice",
        )
        self.assertEqual(registered["status"], "registered")

        concept = self.repo / "wiki/concepts/paper.md"
        concept.write_text(
            """---
type: Concept
title: Paper
description: Durable synthesis of the paper.
status: draft
sources:
  - id: paper
    resource: ../../raw/inbox/paper.md
---

# Paper

Durable claim.[^paper]

[^paper]: Paper source
"""
        )
        indexed = self.run_cli("build_index.py", "--repo", str(self.repo))
        self.assertEqual(indexed["status"], "updated")

        validated = self.run_cli("validate_bundle.py", "--repo", str(self.repo), "--today", "2026-08-15")
        self.assertTrue(validated["ok"])
        guarded = self.run_cli("raw_diff_guard.py", "--repo", str(self.repo))
        self.assertTrue(guarded["ok"])

        run = self.run_cli(
            "write_run_report.py",
            "--repo",
            str(self.repo),
            "--run-id",
            "run-integration",
            "--operation",
            "ingest",
            "--state",
            "PLANNED",
            "--risk",
            "medium",
            "--input",
            "raw/inbox/paper.md",
            "--read",
            "wiki/index.md",
            "--write",
            "wiki/concepts/paper.md",
            "--validation-json",
            '{"name":"bundle","status":"passed"}',
        )
        self.assertEqual(run["status"], "PLANNED")

        source.write_text("tampered\n")
        failed_guard = self.run_cli("raw_diff_guard.py", "--repo", str(self.repo), expected=1)
        self.assertFalse(failed_guard["ok"])

    def test_cli_errors_are_structured(self) -> None:
        result = self.run_cli("validate_bundle.py", "--repo", str(self.repo), expected=2)
        self.assertEqual(result["status"], "error")
        self.assertIn("initialize", result["error"])

        self.run_cli("init_bundle.py", "--repo", str(self.repo))
        (self.repo / ".ad-wiki/source-registry.json").write_text(
            '{"version": 1, "sources": [{"path": "raw/inbox/source.md"}]}\n'
        )
        malformed = self.run_cli("raw_diff_guard.py", "--repo", str(self.repo), expected=2)
        self.assertEqual(malformed["status"], "error")
        self.assertIn("malformed source registry record", malformed["error"])


if __name__ == "__main__":
    unittest.main()
