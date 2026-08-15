# Implementation Plan: Team-distributed AD-Wiki Plugin MVP

Product Contract: in-run alignment from the explicit continuation request “开始实施” and `$ad-harness:ad-lfg`
Requirements: R1-R10
Commit policy / authority: none; the user authorized scoped working-tree edits, not commit, push, PR, marketplace installation, or other external mutation

## Implementation decisions

- Build a repo-local team Marketplace at `.agents/plugins/marketplace.json` and the plugin at `plugins/ad-wiki/`.
- Use the official plugin and skill scaffolders before customization.
- Package one `ad-wiki-maintainer` Skill plus deterministic Python 3 standard-library scripts.
- Keep the MVP dependency-free. Validate the YAML subset emitted by AD-Wiki templates and the OKF structural/profile invariants without claiming support for every YAML feature.
- Keep each knowledge repository independent. The plugin contains workflow capability only; sample knowledge lives under plugin test fixtures, not in the plugin runtime state.
- Exclude MCP, App, external importers, batch ingestion, and Attested Computation runtime from this MVP.
- Keep source registration append-only: new files may be registered; registered bytes may not be modified through AD-Wiki operations.
- Keep write operations local and reviewable. The Skill may prepare changes but may not commit, push, open a PR, or install the Marketplace without explicit authority.

## Scope deltas

None. The implementation follows the accepted Phase 1 scope from the linked design.

## Requirements

- R1 — Team distribution: the repository contains a valid team Marketplace entry for a valid `ad-wiki` Plugin.
- R2 — Agent workflow: the plugin contains a discoverable `ad-wiki-maintainer` Skill covering Init, Ingest, Query, Writeback, Lint, and Migrate with explicit mutation and review boundaries.
- R3 — Initialization: a deterministic command creates the minimum `raw/`, `wiki/`, `.ad-wiki/`, `ad-wiki.yaml`, OKF root index/log, and domain overlay structure without overwriting existing files.
- R4 — Source registration: a deterministic command computes SHA-256, records a canonical locator and version, rejects duplicate content, and refuses mutation of an existing registered source.
- R5 — Validation: a deterministic command distinguishes OKF errors, AD-Wiki profile errors, and quality warnings for frontmatter, reserved files, links, indexes, lifecycle, provenance, and forbidden human verification.
- R6 — Indexing: a deterministic command builds root and nested `index.md` files from Concept metadata with bundle-root links and deterministic ordering.
- R7 — Raw guard: a deterministic command compares registered source hashes with current bytes and fails on mutation or disappearance.
- R8 — Run report: a deterministic command writes a normalized operation record outside the OKF Bundle with allowed states and relative, repository-bounded paths.
- R9 — Reusable assets: the Skill includes concise progressive-disclosure references and templates for Source Summary, Concept, Synthesis, and Open Question.
- R10 — Proof: unit and integration tests cover the success path, idempotency, failure behavior, path isolation, non-overwrite guarantees, plugin/skill validation, and a complete sample lifecycle.

## Implementation units

### U1 — Scaffold and customize the team distribution boundary

- Requirements: R1, R2
- Dependencies and accepted-design pointers: accepted Technical Design sections 3, 7, 8, and 9; official plugin-creator and skill-creator contracts
- Affected modules and mutation: `.agents/plugins/marketplace.json`, `plugins/ad-wiki/.codex-plugin/plugin.json`, `plugins/ad-wiki/skills/ad-wiki-maintainer/`, plugin-level scripts/assets directories
- Entry / exit conditions: enter with an empty repository except user-owned hidden directories; exit with scaffolded paths, real metadata, no TODO placeholders, and no MCP/App declarations
- Focused verification: official `validate_plugin.py`; official `quick_validate.py`; JSON parsing and path checks
- Recovery checkpoint: remove only scaffold files created by U1 if customization cannot be validated; preserve pre-existing `.agents/` and `.claude/`

### U2 — Deliver deterministic knowledge-repository operations test-first

- Requirements: R3-R8
- Dependencies and accepted-design pointers: accepted Technical Design sections 5, 6, 10-14, and 17
- Affected modules and mutation: `plugins/ad-wiki/scripts/ad_wiki/`, six command entrypoints, `plugins/ad-wiki/tests/`
- Entry / exit conditions: enter with a valid plugin shell; exit when init, source registry, validation, index generation, raw guard, and run reports behave through public CLIs
- Focused verification: write failing `unittest` cases first for each behavior slice, implement to green, then run the full script test suite
- Recovery checkpoint: each operation is independently testable and may be reverted without changing the distribution boundary

### U3 — Package the workflow knowledge, templates, and sample bundle

- Requirements: R2, R9
- Dependencies and accepted-design pointers: accepted Technical Design sections 2, 5, 6, 9, 10, 12, and 16
- Affected modules and mutation: Skill `SKILL.md`, `agents/openai.yaml`, `references/`, `assets/templates/`, `examples/minimal-wiki/`
- Entry / exit conditions: enter with operational scripts; exit with concise routing instructions, conditional references, valid templates, and a sample repository that passes validation
- Focused verification: skill quick validation, template fixture tests, and sample bundle validation
- Recovery checkpoint: references and templates are additive and can be revised without altering script contracts

### U4 — Prove the integrated team Plugin MVP

- Requirements: R1-R10
- Dependencies and accepted-design pointers: U1-U3
- Affected modules and mutation: test fixtures and only the smallest fixes required by verification/review
- Entry / exit conditions: enter with all capabilities implemented; exit when official validators, full tests, compile checks, CLI help, and a temporary end-to-end lifecycle all pass
- Focused verification: plugin validator, skill validator, `python -m unittest discover`, `compileall`, init/register/index/validate/raw-guard/run-report sequence in a temporary directory
- Recovery checkpoint: integration fixtures remain isolated from product assets; failures route back to the smallest owning unit

## Verification contract

- Baseline evidence, required: cleanly identify the unborn Git repository and preserve the existing untracked `.agents/` and `.claude/` directories.
- Acceptance evidence, required: all official plugin/skill validators and all repository tests pass with exit code 0.
- Cross-unit evidence, required: a temporary knowledge repository can be initialized, ingest one source registration, generate indexes, validate, guard Raw integrity, and record a run report.
- Release evidence, required: plugin manifest and Marketplace JSON parse; Python sources compile; no TODO placeholders or MCP/App manifests are present.
- Experiential acceptance, preferred: inspect CLI `--help` output and the generated sample Bundle for readable defaults. Owner: engineering in this run.
- Fallback evidence: none. A missing official validator or Python runtime is a real environment limitation and must be reported rather than replaced by lower-fidelity claims.

## Risks and recovery

- YAML breadth: the dependency-free parser intentionally supports the profile subset emitted by bundled templates. It must fail clearly on unsupported syntax rather than silently misread it.
- Existing hidden directories: scaffold operations must not overwrite user-owned files. Inspect exact targets before creation and never use broad cleanup.
- Source immutability: registration and Raw guard must resolve paths inside the selected repository and reject path traversal or symlink escape.
- Index churn: deterministic sorting and generated-file comparison keep repeated index builds idempotent.
- Marketplace identity: use the accepted team name `ad-wiki-team`; do not install it into the user's external Codex configuration in this authority envelope.

## Definition of done

- A fresh teammate can obtain the repo-local Marketplace and a valid `ad-wiki` Plugin artifact.
- The Skill exposes the six accepted workflows and delegates deterministic operations to real scripts.
- The six CLI entrypoints work without third-party Python packages.
- A generated knowledge repository is an OKF v0.2-shaped Bundle with isolated Raw and AD-Wiki runtime state.
- Duplicate registration is idempotent, Raw mutation is detected, indexes are deterministic, and validation categories are explicit.
- All required verification evidence passes.
- The working tree is locally complete with no commit, push, PR, external install, MCP, or App changes.
