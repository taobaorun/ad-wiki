from __future__ import annotations

import json
import os
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
    guard_raw,
    initialize_repository,
    register_source,
    validate_repository,
    write_run_report,
)


class RepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def init_repo(self) -> dict:
        return initialize_repository(self.repo, domain="architecture-decisions")


class InitializeRepositoryTests(RepositoryTestCase):
    def test_creates_minimum_independent_repository(self) -> None:
        result = self.init_repo()

        self.assertEqual(result["status"], "created")
        self.assertTrue((self.repo / "raw/inbox").is_dir())
        self.assertTrue((self.repo / "raw/sources").is_dir())
        self.assertTrue((self.repo / "wiki/sources").is_dir())
        self.assertTrue((self.repo / "wiki/concepts").is_dir())
        self.assertTrue((self.repo / ".ad-wiki/runs").is_dir())

        config = json.loads((self.repo / "ad-wiki.yaml").read_text())
        self.assertEqual(config["profile_version"], "0.1")
        self.assertEqual(config["bundle_root"], "wiki")
        self.assertEqual(config["domain"]["name"], "architecture-decisions")

        index = (self.repo / "wiki/index.md").read_text()
        self.assertIn('okf_version: "0.2"', index)
        self.assertTrue((self.repo / "wiki/log.md").read_text().startswith("# Knowledge Bundle Update Log"))

    def test_is_idempotent_but_never_overwrites_non_identical_files(self) -> None:
        self.init_repo()
        again = self.init_repo()
        self.assertEqual(again["status"], "unchanged")

        config_path = self.repo / "ad-wiki.yaml"
        config_path.write_text("user-owned\n")
        with self.assertRaisesRegex(ADWikiError, "refusing to overwrite"):
            self.init_repo()

    def test_preflights_file_conflicts_before_creating_directories(self) -> None:
        (self.repo / "ad-wiki.yaml").write_text("user-owned\n")

        with self.assertRaisesRegex(ADWikiError, "refusing to overwrite"):
            self.init_repo()

        self.assertFalse((self.repo / "raw").exists())
        self.assertFalse((self.repo / "wiki").exists())

    def test_refuses_initialization_through_escaping_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as outside_directory:
            outside = Path(outside_directory).resolve()
            try:
                (self.repo / ".ad-wiki").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ADWikiError, "initialization path escapes"):
                self.init_repo()
            self.assertEqual(list(outside.iterdir()), [])


class SourceRegistryTests(RepositoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.init_repo()

    def write_source(self, relative: str, text: str) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_registers_idempotently_and_versions_new_paths(self) -> None:
        first_path = self.write_source("raw/inbox/idea-v1.md", "first version\n")
        first = register_source(self.repo, first_path, "https://example.test/idea", "human:alice")
        duplicate = register_source(self.repo, first_path, "https://example.test/idea", "human:alice")

        self.assertEqual(first["status"], "registered")
        self.assertEqual(first["record"]["version"], 1)
        self.assertEqual(duplicate["status"], "unchanged")
        self.assertEqual(duplicate["record"]["source_id"], first["record"]["source_id"])

        second_path = self.write_source("raw/inbox/idea-v2.md", "second version\n")
        second = register_source(self.repo, second_path, "https://example.test/idea", "human:alice")
        self.assertEqual(second["record"]["version"], 2)
        self.assertNotEqual(second["record"]["sha256"], first["record"]["sha256"])

    def test_rejects_duplicate_bytes_registered_under_a_different_locator(self) -> None:
        first_path = self.write_source("raw/inbox/first.md", "same bytes\n")
        second_path = self.write_source("raw/inbox/second.md", "same bytes\n")

        register_source(self.repo, first_path, "urn:test:first")
        with self.assertRaisesRegex(ADWikiError, "duplicate source content"):
            register_source(self.repo, second_path, "urn:test:second")

    def test_rejects_malformed_source_registry_records(self) -> None:
        registry = self.repo / ".ad-wiki/source-registry.json"
        registry.write_text('{"version": 1, "sources": [{"path": "raw/inbox/source.md"}]}\n')

        with self.assertRaisesRegex(ADWikiError, "malformed source registry record"):
            guard_raw(self.repo)

    def test_rejects_mutation_of_an_already_registered_path(self) -> None:
        source = self.write_source("raw/inbox/source.md", "original\n")
        register_source(self.repo, source, "urn:test:source")
        source.write_text("mutated\n")

        with self.assertRaisesRegex(ADWikiError, "registered Raw source changed"):
            register_source(self.repo, source, "urn:test:source")

    def test_rejects_source_outside_raw_or_through_escaping_symlink(self) -> None:
        outside = self.repo / "outside.md"
        outside.write_text("outside\n")
        with self.assertRaisesRegex(ADWikiError, "inside raw"):
            register_source(self.repo, outside, "urn:test:outside")

        link = self.repo / "raw/inbox/link.md"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "inside raw"):
            register_source(self.repo, link, "urn:test:link")

    def test_raw_guard_detects_mutation_and_missing_files(self) -> None:
        source = self.write_source("raw/inbox/source.md", "original\n")
        register_source(self.repo, source, "urn:test:source")
        self.assertTrue(guard_raw(self.repo)["ok"])

        source.write_text("mutated\n")
        changed = guard_raw(self.repo)
        self.assertFalse(changed["ok"])
        self.assertEqual(changed["violations"][0]["code"], "ADW-E301")

        source.unlink()
        missing = guard_raw(self.repo)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["violations"][0]["code"], "ADW-E300")


class IndexAndValidationTests(RepositoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.init_repo()

    def write_concept(self, relative: str, body: str) -> Path:
        path = self.repo / "wiki" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path

    def test_builds_deterministic_bundle_root_indexes(self) -> None:
        self.write_concept(
            "concepts/compilation.md",
            """---
type: Concept
title: Incremental Compilation
description: Compile knowledge once and keep it current.
status: draft
---

# Incremental Compilation
""",
        )

        first = build_indexes(self.repo)
        first_root = (self.repo / "wiki/index.md").read_text()
        first_nested = (self.repo / "wiki/concepts/index.md").read_text()
        second = build_indexes(self.repo)

        self.assertIn('okf_version: "0.2"', first_root)
        self.assertIn("[Incremental Compilation](/concepts/compilation.md)", first_nested)
        self.assertEqual(second["changed"], [])
        self.assertIn("wiki/index.md", first["changed"])

    def test_index_build_refuses_implicit_profile_or_okf_migration(self) -> None:
        config_path = self.repo / "ad-wiki.yaml"
        config = json.loads(config_path.read_text())
        config["profile_version"] = "0.2"
        config_path.write_text(json.dumps(config))
        original_index = (self.repo / "wiki/index.md").read_text()

        with self.assertRaisesRegex(ADWikiError, "profile_version"):
            build_indexes(self.repo)
        self.assertEqual((self.repo / "wiki/index.md").read_text(), original_index)

        config["profile_version"] = "0.1"
        config_path.write_text(json.dumps(config))
        old_index = '---\nokf_version: "0.1"\n---\n\n# Old Bundle\n'
        (self.repo / "wiki/index.md").write_text(old_index)
        with self.assertRaisesRegex(ADWikiError, "OKF version"):
            build_indexes(self.repo)
        self.assertEqual((self.repo / "wiki/index.md").read_text(), old_index)

    def test_valid_bundle_passes_with_quality_warnings_allowed(self) -> None:
        self.write_concept(
            "concepts/a.md",
            """---
type: Concept
title: A
description: A valid concept.
generated:
  by: ad-wiki/0.1.0
  at: 2026-08-15T10:00:00Z
status: draft
sources:
  - id: source-a
    resource: https://example.test/a
---

# A

Claim A.[^source-a]

[^source-a]: Source A
""",
        )
        build_indexes(self.repo)
        report = validate_repository(self.repo, today=date(2026, 8, 15))

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["errors"], [])

    def test_classifies_okf_errors_profile_errors_and_quality_warnings(self) -> None:
        self.write_concept("concepts/no-frontmatter.md", "# Missing\n")
        self.write_concept(
            "concepts/bad-status.md",
            """---
type: Concept
title: Bad status
status: published
stale_after: 2026-01-01
---

[Missing target](/concepts/does-not-exist.md)
""",
        )
        (self.repo / "wiki/log.md").write_text("# Knowledge Bundle Update Log\n\n## [2026-08-15]\n")
        report = validate_repository(self.repo, today=date(2026, 8, 15))

        error_codes = {item["code"] for item in report["errors"]}
        warning_codes = {item["code"] for item in report["warnings"]}
        self.assertIn("OKF-E001", error_codes)
        self.assertIn("ADW-E101", error_codes)
        self.assertIn("OKF-E020", error_codes)
        self.assertIn("ADW-W201", warning_codes)
        self.assertIn("ADW-W210", warning_codes)

    def test_claim_source_ids_and_index_coverage_are_checked(self) -> None:
        self.write_concept(
            "concepts/claim.md",
            """---
type: Concept
title: Claim
sources:
  - id: declared
    resource: https://example.test/declared
---

Unsupported citation.[^missing]

[^missing]: Missing source
""",
        )
        report = validate_repository(self.repo, today=date(2026, 8, 15))
        error_codes = {item["code"] for item in report["errors"]}
        warning_codes = {item["code"] for item in report["warnings"]}
        self.assertIn("ADW-E220", error_codes)
        self.assertIn("ADW-W230", warning_codes)

    def test_rejects_unsupported_inline_source_syntax_explicitly(self) -> None:
        self.write_concept(
            "concepts/inline.md",
            """---
type: Concept
title: Inline source syntax
sources: [{id: source-a, resource: https://example.test/a}]
---

# Inline source syntax
""",
        )

        report = validate_repository(self.repo, today=date(2026, 8, 15))
        self.assertIn("ADW-E111", {item["code"] for item in report["errors"]})

    def test_rejects_unsupported_block_scalar_syntax_explicitly(self) -> None:
        self.write_concept(
            "concepts/block-scalar.md",
            """---
type: Concept
description: >
  This parser intentionally supports only the bundled profile subset.
---

# Block scalar
""",
        )

        report = validate_repository(self.repo, today=date(2026, 8, 15))
        self.assertIn("OKF-E004", {item["code"] for item in report["errors"]})

    def test_rejects_concept_symlinks_that_escape_the_bundle(self) -> None:
        outside = self.repo / "outside.md"
        outside.write_text("---\ntype: Concept\n---\n\n# Outside\n")
        link = self.repo / "wiki/concepts/outside.md"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")

        report = validate_repository(self.repo, today=date(2026, 8, 15))
        self.assertIn("ADW-E121", {item["code"] for item in report["errors"]})
        with self.assertRaisesRegex(ADWikiError, "escapes Bundle"):
            build_indexes(self.repo)

    def test_requires_profile_directories_and_reserved_root_files(self) -> None:
        (self.repo / "wiki/index.md").unlink()
        (self.repo / "wiki/log.md").unlink()

        report = validate_repository(self.repo, today=date(2026, 8, 15))
        error_codes = {item["code"] for item in report["errors"]}
        self.assertIn("OKF-E010", error_codes)
        self.assertIn("ADW-E103", error_codes)

    def test_validates_verification_events_without_rejecting_real_human_review(self) -> None:
        self.write_concept(
            "concepts/reviewed.md",
            """---
type: Concept
title: Reviewed
verified: { by: human:alice, at: 2026-08-15T10:00:00Z }
---

# Reviewed
""",
        )
        self.write_concept(
            "concepts/bad-verification.md",
            """---
type: Concept
title: Bad verification
verified:
  - by: human:bob
---

# Bad verification
""",
        )

        report = validate_repository(self.repo, today=date(2026, 8, 15))
        verification_errors = [item for item in report["errors"] if item["code"] == "ADW-E112"]
        self.assertEqual(len(verification_errors), 1, report)
        self.assertEqual(verification_errors[0]["path"], "wiki/concepts/bad-verification.md")

    def test_rejects_invalid_executable_repository_policy(self) -> None:
        config_path = self.repo / "ad-wiki.yaml"
        config = json.loads(config_path.read_text())
        config["lint"]["broken_links"] = "sometimes"
        config["ingest"]["max_batch_size"] = 0
        config["review"]["owners"] = ["not an actor"]
        config["search"]["provider"] = "uninstalled-mcp"
        config_path.write_text(json.dumps(config))

        report = validate_repository(self.repo, today=date(2026, 8, 15))
        codes = [item["code"] for item in report["errors"]]
        self.assertIn("ADW-E107", codes)
        self.assertGreaterEqual(codes.count("ADW-E109"), 3)


class RunReportTests(RepositoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.init_repo()

    def test_writes_and_advances_valid_state_transitions(self) -> None:
        created = write_run_report(
            self.repo,
            run_id="run-20260815-001",
            operation="ingest",
            state="PLANNED",
            risk="medium",
            inputs=["raw/inbox/source.md"],
            read_set=["wiki/index.md"],
            write_set=["wiki/sources/source.md"],
            validations=[],
        )
        advanced = write_run_report(
            self.repo,
            run_id="run-20260815-001",
            operation="ingest",
            state="APPROVED",
            risk="medium",
            inputs=["raw/inbox/source.md"],
            read_set=["wiki/index.md"],
            write_set=["wiki/sources/source.md"],
            validations=[{"name": "plan-review", "status": "passed"}],
        )

        self.assertEqual(created["status"], "PLANNED")
        self.assertEqual(advanced["status"], "APPROVED")
        stored = json.loads((self.repo / ".ad-wiki/runs/run-20260815-001/run.json").read_text())
        self.assertEqual(stored["status"], "APPROVED")

        with self.assertRaisesRegex(ADWikiError, "invalid state transition"):
            write_run_report(
                self.repo,
                run_id="run-20260815-001",
                operation="ingest",
                state="PLANNED",
                risk="medium",
                inputs=[],
                read_set=[],
                write_set=[],
                validations=[],
            )

    def test_rejects_invalid_run_ids_and_escaping_paths(self) -> None:
        with self.assertRaisesRegex(ADWikiError, "invalid run id"):
            write_run_report(
                self.repo,
                run_id="../escape",
                operation="lint",
                state="PLANNED",
                risk="low",
                inputs=[],
                read_set=[],
                write_set=[],
                validations=[],
            )

        with self.assertRaisesRegex(ADWikiError, "outside repository"):
            write_run_report(
                self.repo,
                run_id="run-safe",
                operation="lint",
                state="PLANNED",
                risk="low",
                inputs=["../escape"],
                read_set=[],
                write_set=[],
                validations=[],
            )


if __name__ == "__main__":
    unittest.main()
