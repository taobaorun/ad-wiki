# Implementation Plan: AD-Wiki Team-Usable v0.2

Product Contract: in-run continuation of the user request “现在我们实现完成可用的版本”
Technical Design: `docs/designs/ad-wiki-team-workflow.md`
Requirements: R1-R10
Commit policy / authority: none; this request authorizes scoped working-tree edits, not commit, push, PR, Marketplace installation, or external mutation

## Implementation decisions

- Define “usable” as a teammate being able to install the Plugin artifact, initialize an independent repository, prepare and safely apply one supervised knowledge mutation, query the resulting Bundle, lint it, review the run, and repeat the flow in a second repository without cross-library access.
- Keep Search MCP, a management App, external importers, batch ingestion, and Attested Computation runtime outside this release. They remain optional scale features, not prerequisites for the single-repository loop.
- Keep OKF `0.2` and AD-Wiki Profile `0.1` stable. Release the Plugin as `0.2.0`; do not invent a content migration merely to align version numbers.
- Preserve the Skill-centered boundary: the Agent owns semantic reading and synthesis; deterministic scripts own repository resolution, source integrity, search candidates, policy severity, run state, locks, baseline drift, staged application, rollback, indexes, logs, and validation.
- Stage semantic writes under `.ad-wiki/runs/<run-id>/staged/` and apply only the exact planned write set. Never let the Plugin modify registered Raw files.
- Use an exclusive `.ad-wiki/lock` for writers. Recheck read/write baselines immediately before application and roll back in-process failures to the pre-apply bytes.
- Keep `ad-wiki.yaml` JSON-compatible YAML for the dependency-free runtime. Enforce configured Lint severities and domain Concept types instead of treating those fields as decorative.
- Provide a built-in lexical search command for the Phase-1 scale. Markdown remains authoritative and the command returns Concept paths plus source metadata; it does not generate an answer or mutate knowledge.
- Provide an explicit migration command that reports an already-current Profile and refuses unsupported source/target pairs. New deterministic migration functions can be registered when a real Profile version exists.

## Scope deltas

- The accepted design names six MVP scripts. This release adds focused command entrypoints for prepare, approve, apply, review, search, and migrate because the earlier six utilities cannot enforce the designed transaction and query boundaries by themselves. The Plugin remains dependency-free and Skill-centered.
- Actual installation into the user’s persistent Codex configuration is not authorized. Release proof uses official Plugin/Skill validators and an isolated marketplace-layout test; the final handoff will identify live installation as human acceptance if it cannot be exercised without mutating user configuration.

## Implementation units

### U1 — Make repository configuration executable policy

- Requirements: R2, R7
- Dependencies and accepted-design pointers: Technical Design sections 6, 12, 14, and 17
- Affected modules and mutation: `scripts/ad_wiki/core.py`, validation tests, initialized/sample configuration
- Entry / exit conditions: enter with configuration used only for roots/version; exit with validated config shape, configured Lint severities, domain type findings, and repository-bounded paths
- Focused verification: unit tests for `error | warning | ignore`, invalid configuration, distinct repository policies, and path/symlink escape
- Recovery checkpoint: validation policy changes are isolated from transaction application

### U2 — Deliver a recoverable write transaction

- Requirements: R3, R4, R6, R8, R9
- Dependencies and accepted-design pointers: Technical Design sections 10-13 and risk/migration references
- Affected modules and mutation: core transaction/run APIs; prepare, approve, apply, review, and migrate CLIs; Skill workflow references
- Entry / exit conditions: enter with free-form run reports; exit when a planned staged write is baseline-bound, approval-gated, lock-protected, automatically indexed/logged/validated, and rolled back on drift or validation failure
- Focused verification: success, duplicate/idempotent transitions, high-risk approval, lock contention, unplanned staged paths, Raw mutation, baseline drift, validation rollback, and truthful failure status
- Recovery checkpoint: every test uses a temporary repository; failed application restores pre-apply Bundle bytes

### U3 — Make Query and semantic operations operational

- Requirements: R4, R5, R6, R7
- Dependencies and accepted-design pointers: Technical Design sections 10 and 15; LLM-Wiki index-first semantics
- Affected modules and mutation: built-in search API/CLI, Maintainer Skill, workflow and risk references, templates
- Entry / exit conditions: enter with narrative Query/Ingest/Writeback instructions; exit with deterministic candidate retrieval and one exact staged-write protocol shared by Ingest, Writeback, and authorized Lint repair
- Focused verification: ranked Concept/source results, no mutation on Query, claim/source metadata, complete write-set enforcement, and log/index updates
- Recovery checkpoint: search is read-only and transaction entrypoints remain independently removable

### U4 — Prove team distribution and two-repository isolation

- Requirements: R1-R10
- Dependencies and accepted-design pointers: U1-U3 and Technical Design sections 3, 7, 8, 18, and 20
- Affected modules and mutation: Plugin metadata, example Bundle, packaging/integration/evaluation tests
- Entry / exit conditions: enter with the v0.1 scaffold; exit when official validators, full tests, compile/help checks, two independent repository journeys, and a fresh-context Skill forward test pass
- Focused verification: official `validate_plugin.py` and `quick_validate.py`; full `unittest`; temporary lifecycle for two repos; manifest/Marketplace parsing; independent Agent forward test
- Recovery checkpoint: all acceptance repositories are temporary and no persistent Marketplace installation is performed

## Verification contract

- Baseline evidence, required: bind checks to the feature branch plus the exact changed paths; preserve untracked `.agents/skills/` and `.claude/`.
- Acceptance evidence, required: official Plugin/Skill validators; full test suite; compile and CLI help; transaction success/rollback; search read-only behavior; two-repository isolation.
- Cross-unit evidence, required: initialize, register, prepare, stage, approve, apply, validate, query, review, and Raw guard in a temporary repository, with a second repository remaining byte-identical.
- Release evidence, required: Plugin/Marketplace JSON parse, Plugin version `0.2.0`, no undeclared MCP/App capability, no placeholders, dependency-free Python sources.
- Experiential acceptance, preferred: fresh-context Agent uses the packaged Skill against a temporary repository. Owner: engineering for mechanics; a real teammate owns persistent install/UX acceptance.
- Fallback evidence: official static validators replace live persistent installation only because the current authority forbids modifying the user’s Codex configuration; this proves package structure, not end-user discovery UX.

## Risks and recovery

- Multi-file writes cannot be crash-atomic on a plain filesystem. The release guarantees exclusive writers, pre-apply drift detection, atomic per-file replacement, and in-process rollback; Git remains the durable recovery boundary.
- Semantic correctness cannot be proven by deterministic scripts. Forward tests verify the Skill follows the protocol, while human review remains explicit for medium/high-risk conclusions.
- Stricter configured Lint severity can expose existing repository debt. Validation reports exact codes and never mutates during Lint.
- Run approvals are auditable assertions, not identity authentication. The Skill must never fabricate a human actor; repository permissions and review systems remain the authority boundary.

## Definition of done

- A valid `ad-wiki` `0.2.0` Plugin exposes Init, Ingest, Query, Writeback, Lint, and Migrate with deterministic supporting commands.
- One supervised source can be registered and semantically staged, then applied only after risk-appropriate approval with lock, baseline, Raw, index, log, validation, and rollback guarantees.
- Query returns repository-local Concept candidates with source metadata and makes no writes.
- Configured Lint policies and domain types affect validation output.
- Run states cannot skip required gates or claim validation/review without corresponding evidence.
- Two independent repositories can use different policies without cross-read or cross-write behavior.
- All required verification passes; persistent team installation and content acceptance remain truthfully assigned to a human owner.
