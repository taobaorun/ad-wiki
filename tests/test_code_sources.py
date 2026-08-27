from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ad_wiki.code_sources import (  # noqa: E402
    bind_code_worktree,
    inspect_code_repository,
    load_code_source_registry,
    normalize_remote,
    rebuild_code_source_registry,
    repository_key,
    resolve_code_worktree,
)
from ad_wiki.core import ADWikiError, initialize_repository, validate_repository  # noqa: E402
from ad_wiki.locking import repository_lock  # noqa: E402


class CodeSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        self.wiki = self.root / "wiki"
        self.code = self.root / "code"
        initialize_repository(self.wiki, "research")
        self._init_code_repo(self.code, "https://example.test/framework.git")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or self.code,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return result.stdout.strip()

    def run_cli(self, script: str, *args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / script), *args, "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def _init_code_repo(self, path: Path, remote: str) -> None:
        path.mkdir()
        self.git("init", "-b", "main", cwd=path)
        self.git("config", "user.name", "AD Wiki Test", cwd=path)
        self.git("config", "user.email", "ad-wiki@example.test", cwd=path)
        (path / "README.md").write_text(f"framework {path.name}\n")
        self.git("add", ".", cwd=path)
        self.git("commit", "-m", "initial", cwd=path)
        self.git("remote", "add", "origin", remote, cwd=path)

    def test_normalizes_only_portable_noncredentialed_remotes(self) -> None:
        self.assertEqual(
            normalize_remote("git@example.test:org/repo.git"),
            "ssh://git@example.test/org/repo",
        )
        self.assertEqual(
            normalize_remote("https://example.test/org/repo.git/"),
            "https://example.test/org/repo",
        )
        self.assertIsNone(normalize_remote("https://token@example.test/org/repo.git"))
        self.assertIsNone(normalize_remote("https://user:secret@example.test/org/repo.git"))
        self.assertIsNone(normalize_remote(str(self.code)))
        self.assertIsNone(normalize_remote("file:///tmp/repo"))

    def test_inspection_preserves_clean_default_and_can_report_dirty(self) -> None:
        clean = inspect_code_repository(self.code)
        self.assertTrue(clean["worktree_clean"])
        self.assertEqual(clean["remote"], "https://example.test/framework")

        (self.code / "dirty.txt").write_text("dirty\n")
        with self.assertRaisesRegex(ADWikiError, "clean Git worktree"):
            inspect_code_repository(self.code)
        self.assertFalse(
            inspect_code_repository(self.code, require_clean=False)["worktree_clean"]
        )

    def test_binds_privately_resolves_exactly_and_never_selects_ambiguity(self) -> None:
        self.git("init", "-b", "main", cwd=self.wiki)
        self.git("config", "user.name", "AD Wiki Test", cwd=self.wiki)
        self.git("config", "user.email", "ad-wiki@example.test", cwd=self.wiki)
        self.git("add", ".", cwd=self.wiki)
        self.git("commit", "-m", "wiki", cwd=self.wiki)

        first = bind_code_worktree(self.wiki, code_repo=self.code)
        revision = first["code_source"]["revision"]
        resolved = resolve_code_worktree(
            self.wiki,
            canonical_remote="https://example.test/framework.git",
            revision=revision,
            require_clean=True,
        )
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolution"]["path"], str(self.code))
        self.assertEqual(resolved["resolution"]["read_mode"], "git-object")
        self.assertEqual(resolved["resolution"]["read_revision"], revision)
        self.assertEqual(self.git("status", "--short", cwd=self.wiki), "")
        bindings = self.wiki / ".ad-wiki/cache/code-worktrees/bindings.json"
        self.assertTrue(bindings.is_file())
        self.assertEqual(bindings.stat().st_mode & 0o777, 0o600)

        second = self.root / "code-second"
        self._init_code_repo(second, "https://example.test/framework.git")
        bind_code_worktree(self.wiki, code_repo=second)
        ambiguous = resolve_code_worktree(
            self.wiki,
            canonical_remote="https://example.test/framework",
        )
        self.assertEqual(ambiguous["status"], "ambiguous")
        self.assertEqual(len(ambiguous["candidates"]), 2)
        filtered = resolve_code_worktree(
            self.wiki,
            canonical_remote="https://example.test/framework",
            revision=revision,
        )
        self.assertEqual(filtered["status"], "resolved")
        self.assertEqual(filtered["resolution"]["path"], str(self.code))

    def test_resolution_fails_closed_for_wrong_remote_dirty_and_symlink(self) -> None:
        bind_code_worktree(self.wiki, code_repo=self.code)
        self.git("remote", "set-url", "origin", "https://example.test/other.git")
        missing = resolve_code_worktree(
            self.wiki,
            canonical_remote="https://example.test/framework",
        )
        self.assertEqual(missing["status"], "missing")
        self.assertIn("canonical remote changed", " ".join(missing["diagnostics"]))

        self.git("remote", "set-url", "origin", "https://example.test/framework.git")
        (self.code / "dirty.txt").write_text("dirty\n")
        dirty = resolve_code_worktree(
            self.wiki,
            canonical_remote="https://example.test/framework",
            require_clean=True,
        )
        self.assertEqual(dirty["status"], "missing")
        self.assertIn("worktree is dirty", " ".join(dirty["diagnostics"]))

        link = self.root / "code-link"
        try:
            link.symlink_to(self.code, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "must not use a symlink"):
            bind_code_worktree(self.wiki, code_repo=link)

    def test_resolution_rejects_same_remote_after_repository_root_replacement(self) -> None:
        bind_code_worktree(self.wiki, code_repo=self.code)
        self.git("switch", "--orphan", "replacement")
        (self.code / "README.md").write_text("replacement root\n")
        self.git("add", "-A")
        self.git("commit", "-m", "replacement")

        result = resolve_code_worktree(
            self.wiki,
            canonical_remote="https://example.test/framework",
        )

        self.assertEqual(result["status"], "missing")
        self.assertIn("repository root identity changed", " ".join(result["diagnostics"]))

    def test_historical_revision_resolution_requires_git_object_reads(self) -> None:
        bound = bind_code_worktree(self.wiki, code_repo=self.code)
        historical = bound["code_source"]["revision"]
        (self.code / "README.md").write_text("new head\n")
        self.git("add", "README.md")
        self.git("commit", "-m", "advance")
        current = self.git("rev-parse", "HEAD")

        result = resolve_code_worktree(
            self.wiki,
            canonical_remote="https://example.test/framework",
            revision=historical,
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["resolution"]["read_mode"], "git-object")
        self.assertEqual(result["resolution"]["read_revision"], historical)
        self.assertEqual(result["resolution"]["code_source"]["revision"], current)

    def test_binding_rejects_parent_or_final_cache_symlink_and_damaged_ignore(self) -> None:
        leak = self.wiki / "wiki/leak"
        leak.mkdir()
        cache = self.wiki / ".ad-wiki/cache"
        try:
            cache.symlink_to(leak, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "cache path must not use a symlink"):
            bind_code_worktree(self.wiki, code_repo=self.code)
        self.assertFalse((leak / "code-worktrees/bindings.json").exists())

        cache.unlink()
        cache.mkdir()
        final = cache / "code-worktrees"
        final.symlink_to(leak, target_is_directory=True)
        with self.assertRaisesRegex(ADWikiError, "cache path must not use a symlink"):
            bind_code_worktree(self.wiki, code_repo=self.code)
        self.assertFalse((leak / "bindings.json").exists())

        final.unlink()
        final.mkdir()
        (final / ".gitignore").write_text("lock\n")
        with self.assertRaisesRegex(ADWikiError, "gitignore contract changed"):
            bind_code_worktree(self.wiki, code_repo=self.code)
        self.assertFalse((final / "bindings.json").exists())

    def test_binding_and_rebuild_share_repository_writer_exclusion(self) -> None:
        registry_path = self.wiki / ".ad-wiki/code-source-registry.json"
        original = registry_path.read_bytes()
        with repository_lock(self.wiki, "test-holder"):
            with self.assertRaisesRegex(ADWikiError, "another AD-Wiki writer"):
                bind_code_worktree(self.wiki, code_repo=self.code)
            with self.assertRaisesRegex(ADWikiError, "another AD-Wiki writer"):
                rebuild_code_source_registry(self.wiki)

        self.assertEqual(registry_path.read_bytes(), original)
        self.assertFalse(
            (self.wiki / ".ad-wiki/cache/code-worktrees/bindings.json").exists()
        )

    def test_mutators_reject_non_wiki_targets_without_creating_state(self) -> None:
        for target in (self.root / "missing-wiki", self.root / "plain-directory"):
            if target.name == "plain-directory":
                target.mkdir()
            with self.subTest(target=target):
                with self.assertRaisesRegex(ADWikiError, "ad-wiki.yaml not found"):
                    bind_code_worktree(target, code_repo=self.code)
                with self.assertRaisesRegex(ADWikiError, "ad-wiki.yaml not found"):
                    rebuild_code_source_registry(target)
                self.assertFalse((target / ".ad-wiki").exists())

                cli_result = self.run_cli(
                    "bind_code_worktree.py",
                    "--repo",
                    str(target),
                    "--code-repo",
                    str(self.code),
                    expected=2,
                )
                self.assertEqual(cli_result["status"], "error")
                self.assertFalse((target / ".ad-wiki").exists())

    def test_local_remote_uses_root_identity_without_leaking_portable_path(self) -> None:
        self.git("remote", "set-url", "origin", str(self.root / "bare.git"))
        bound = bind_code_worktree(self.wiki, code_repo=self.code)
        source = bound["code_source"]
        self.assertIsNone(source["remote"])
        key = repository_key(source)
        resolved = resolve_code_worktree(self.wiki, repository_key=key)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(load_code_source_registry(self.wiki), {"sources": [], "version": 1})

    def test_rejects_malformed_portable_registry_without_touching_bindings(self) -> None:
        path = self.wiki / ".ad-wiki/code-source-registry.json"
        path.write_text(json.dumps({"sources": [{"repository_key": "bad"}], "version": 1}))
        with self.assertRaisesRegex(ADWikiError, "malformed code source registry"):
            load_code_source_registry(self.wiki)

        for version in (True, False, 1.0, "1"):
            with self.subTest(version=version):
                path.write_text(json.dumps({"sources": [], "version": version}))
                with self.assertRaisesRegex(ADWikiError, "unsupported code source registry"):
                    load_code_source_registry(self.wiki)

        wrong_types = (
            {
                "sources": [
                    {
                        "canonical_remote": 7,
                        "repository": "framework",
                        "repository_key": "0" * 16,
                        "root_commits": ["0" * 40],
                        "snapshots": [],
                    }
                ],
                "version": 1,
            },
            {
                "sources": [
                    {
                        "canonical_remote": None,
                        "repository": ["framework"],
                        "repository_key": "0" * 16,
                        "root_commits": ["0" * 40],
                        "snapshots": [],
                    }
                ],
                "version": 1,
            },
            {
                "sources": [
                    {
                        "canonical_remote": None,
                        "repository": "framework",
                        "repository_key": repository_key(
                            {
                                "remote": None,
                                "repository": "framework",
                                "root_commits": ["0" * 40],
                            }
                        ),
                        "root_commits": ["0" * 40],
                        "snapshots": [
                            {
                                "revision": "0" * 40,
                                "source_summary_path": 7,
                                "validated_run_id": "run",
                            }
                        ],
                    }
                ],
                "version": 1,
            },
        )
        for value in wrong_types:
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ADWikiError, "malformed code source"):
                    load_code_source_registry(self.wiki)
                report = validate_repository(self.wiki)
                self.assertFalse(report["ok"])
                self.assertIn("ADW-E310", {item["code"] for item in report["errors"]})
        path.write_text(
            json.dumps({"host_path": "/Users/private", "sources": [], "version": 1})
        )
        with self.assertRaisesRegex(ADWikiError, "unsupported code source registry"):
            load_code_source_registry(self.wiki)

        remote = "https://example.test/framework"
        identity = {"remote": remote, "repository": "/Users/private/framework", "root_commits": ["0" * 40]}
        path.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "canonical_remote": remote,
                            "repository": identity["repository"],
                            "repository_key": repository_key(identity),
                            "root_commits": identity["root_commits"],
                            "snapshots": [],
                        }
                    ],
                    "version": 1,
                }
            )
        )
        with self.assertRaisesRegex(ADWikiError, "malformed code source registry"):
            load_code_source_registry(self.wiki)

    def test_code_source_cli_binds_resolves_and_rebuilds_without_runs(self) -> None:
        bound = self.run_cli(
            "bind_code_worktree.py",
            "--repo",
            str(self.wiki),
            "--code-repo",
            str(self.code),
        )
        resolved = self.run_cli(
            "resolve_code_worktree.py",
            "--repo",
            str(self.wiki),
            "--canonical-remote",
            bound["code_source"]["remote"],
            "--revision",
            bound["code_source"]["revision"],
            "--require-clean",
        )
        self.assertEqual(resolved["status"], "resolved")
        rebuilt = self.run_cli(
            "rebuild_code_source_registry.py",
            "--repo",
            str(self.wiki),
        )
        self.assertEqual(rebuilt["registry"], {"sources": [], "version": 1})
        first_bytes = (self.wiki / ".ad-wiki/code-source-registry.json").read_bytes()
        self.run_cli(
            "rebuild_code_source_registry.py",
            "--repo",
            str(self.wiki),
        )
        self.assertEqual(
            (self.wiki / ".ad-wiki/code-source-registry.json").read_bytes(),
            first_bytes,
        )

    def test_private_binding_version_requires_exact_integer(self) -> None:
        bound = bind_code_worktree(self.wiki, code_repo=self.code)
        path = self.wiki / ".ad-wiki/cache/code-worktrees/bindings.json"
        original = json.loads(path.read_text())
        for version in (True, False, 1.0, "1"):
            with self.subTest(version=version):
                path.write_text(json.dumps({**original, "version": version}))
                with self.assertRaisesRegex(ADWikiError, "unsupported code worktree binding"):
                    resolve_code_worktree(
                        self.wiki,
                        canonical_remote=bound["code_source"]["remote"],
                    )

    def test_rebuild_sanitizes_legacy_local_remote_without_inventing_path(self) -> None:
        source = inspect_code_repository(self.code)
        summary = self.wiki / "wiki/sources/code-framework.md"
        summary.write_text("# Framework code snapshot\n")
        run_dir = self.wiki / ".ad-wiki/runs/legacy-local"
        run_dir.mkdir(parents=True)
        report = {
            "code_wiki": {
                "code_source": {
                    **source,
                    "remote": "/Users/private/framework",
                },
                "source_summary_path": "wiki/sources/code-framework.md",
            },
            "events": [{"at": "2026-08-27T00:00:00Z", "state": "VALIDATED"}],
            "inputs": [],
            "operation": "code-wiki",
            "read_set": [],
            "risk": "medium",
            "run_id": "legacy-local",
            "status": "VALIDATED",
            "validations": [],
            "write_set": [],
        }
        (run_dir / "run.json").write_text(json.dumps(report))

        rebuilt = self.run_cli(
            "rebuild_code_source_registry.py",
            "--repo",
            str(self.wiki),
        )

        record = rebuilt["registry"]["sources"][0]
        self.assertIsNone(record["canonical_remote"])
        self.assertNotIn("/Users/private", json.dumps(rebuilt))

    def test_rebuild_derives_safe_name_instead_of_copying_legacy_repository_path(self) -> None:
        source = inspect_code_repository(self.code)
        summary = self.wiki / "wiki/sources/code-framework.md"
        summary.write_text("# Framework code snapshot\n")
        run_dir = self.wiki / ".ad-wiki/runs/legacy-remote"
        run_dir.mkdir(parents=True)
        report = {
            "code_wiki": {
                "code_source": {
                    **source,
                    "repository": "/Users/private/framework",
                },
                "source_summary_path": "wiki/sources/code-framework.md",
            },
            "inputs": [],
            "operation": "code-wiki",
            "read_set": [],
            "risk": "medium",
            "run_id": "legacy-remote",
            "status": "VALIDATED",
            "validations": [],
            "write_set": [],
        }
        (run_dir / "run.json").write_text(json.dumps(report))

        rebuilt = self.run_cli(
            "rebuild_code_source_registry.py",
            "--repo",
            str(self.wiki),
        )

        record = rebuilt["registry"]["sources"][0]
        self.assertEqual(record["repository"], "framework")
        self.assertNotIn("/Users/private", json.dumps(rebuilt))

    def test_rebuild_rejects_incomplete_legacy_provenance_without_mutating_registry(self) -> None:
        registry_path = self.wiki / ".ad-wiki/code-source-registry.json"
        original = registry_path.read_bytes()
        summary = self.wiki / "wiki/sources/code-invalid.md"
        summary.write_text("# Invalid code snapshot\n")
        run_dir = self.wiki / ".ad-wiki/runs/incomplete"
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(
            json.dumps(
                {
                    "code_wiki": {
                        "code_source": {"remote": 7},
                        "source_summary_path": "wiki/sources/code-invalid.md",
                    },
                    "inputs": [],
                    "operation": "code-wiki",
                    "read_set": [],
                    "risk": "medium",
                    "run_id": "incomplete",
                    "status": "VALIDATED",
                    "validations": [],
                    "write_set": [],
                }
            )
        )

        result = self.run_cli(
            "rebuild_code_source_registry.py",
            "--repo",
            str(self.wiki),
            expected=2,
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("malformed code source provenance", result["error"])
        self.assertEqual(registry_path.read_bytes(), original)

    def test_rebuild_rejects_malformed_historical_run_without_erasing_registry(self) -> None:
        registry_path = self.wiki / ".ad-wiki/code-source-registry.json"
        original = registry_path.read_bytes()
        run_dir = self.wiki / ".ad-wiki/runs/malformed"
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text("{not-json\n")

        result = self.run_cli(
            "rebuild_code_source_registry.py",
            "--repo",
            str(self.wiki),
            expected=2,
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("invalid historical run report", result["error"])
        self.assertEqual(registry_path.read_bytes(), original)

    def test_rebuild_rejects_json_valid_malformed_run_envelopes(self) -> None:
        registry_path = self.wiki / ".ad-wiki/code-source-registry.json"
        original = registry_path.read_bytes()
        for index, payload in enumerate(([], {"run_id": "wrong"})):
            with self.subTest(payload=payload):
                run_dir = self.wiki / f".ad-wiki/runs/malformed-{index}"
                run_dir.mkdir(parents=True)
                (run_dir / "run.json").write_text(json.dumps(payload))
                with self.assertRaisesRegex(ADWikiError, "malformed historical run"):
                    rebuild_code_source_registry(self.wiki)
                self.assertEqual(registry_path.read_bytes(), original)
                shutil.rmtree(run_dir)

    def test_registry_and_source_summary_lexical_symlinks_fail_closed(self) -> None:
        registry_path = self.wiki / ".ad-wiki/code-source-registry.json"
        registry_path.unlink()
        leak = self.wiki / "wiki/registry-leak.json"
        try:
            registry_path.symlink_to(leak)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ADWikiError, "registry path must not use a symlink"):
            rebuild_code_source_registry(self.wiki)
        self.assertFalse(leak.exists())
        validation = validate_repository(self.wiki)
        self.assertFalse(validation["ok"])
        self.assertIn("ADW-E310", {item["code"] for item in validation["errors"]})

        registry_path.unlink()
        registry_path.write_text(json.dumps({"sources": [], "version": 1}))
        target = self.wiki / "wiki/sources/code-target.md"
        target.write_text("# Target\n")
        link = self.wiki / "wiki/sources/code-link.md"
        link.symlink_to(target)
        run_id = "symlink-summary"
        run_dir = self.wiki / f".ad-wiki/runs/{run_id}"
        run_dir.mkdir(parents=True)
        source = inspect_code_repository(self.code)
        (run_dir / "run.json").write_text(
            json.dumps(
                {
                    "code_wiki": {
                        "code_source": source,
                        "source_summary_path": "wiki/sources/code-link.md",
                    },
                    "inputs": [],
                    "operation": "code-wiki",
                    "read_set": [],
                    "risk": "medium",
                    "run_id": run_id,
                    "status": "VALIDATED",
                    "validations": [],
                    "write_set": [],
                }
            )
        )
        original = registry_path.read_bytes()
        with self.assertRaisesRegex(ADWikiError, "summary path must not use a symlink"):
            rebuild_code_source_registry(self.wiki)
        self.assertEqual(registry_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
