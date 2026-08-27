# Technical Design: Reviewed Writeback and Code Source Resolution

Design identity: `ad-wiki-reviewed-writeback-code-source-resolution-v1`

Product Contract: `docs/product-specs/ad-wiki-reviewed-writeback-and-code-source-resolution.md`

Requirements covered: R-WB1–R-WB11, R-CS1–R-CS6

Authority: accepted on 2026-08-27 by `ad-gallop` within the Product Contract's delegated engineering defaults. No product decision remains open.

## Current behavior, constraints, and invariants

- Query is read-only and may emit a conversational writeback candidate, but its current contract has no lifecycle for a candidate that changes across turns.
- Generic `prepare_run` creates a `PLANNED` run and staging directory. `apply_run` accepts `PLANNED` directly, computes staged SHA-256 hashes, checks the repository baseline and Raw integrity, locks, applies, rebuilds indexes/log, validates, and rolls back on failure.
- The state model already contains `REVIEW_REQUIRED`, and `apply_run` already accepts it, but no current command freezes a generic staged candidate or moves a run into that state.
- Code Wiki has the useful precedent: `finalize_code_wiki` freezes `finalized_staged_hashes`; generic Writeback has no equivalent.
- `approve_run.py` is a deprecated no-op. Legacy `APPROVED`/`AUTO_APPROVED` runs and `approved_staged_hashes` remain readable compatibility data. `review_run` is post-Apply only.
- `inspect_code_repository` validates a Git worktree and records normalized remote, repository basename, HEAD revision, root commits, and clean status. It deliberately does not persist the local path.
- `.ad-wiki/source-registry.json` is exclusively the immutable Raw registry. Existing Code Wiki run reports and Source Summaries carry portable Git remote/revision provenance, but no direct portable registry or host-local worktree binding exists.
- Standalone Wiki Skill delivery excludes `.ad-wiki/runs` and `.ad-wiki/cache`; Source Summaries remain the delivered code provenance surface.
- The implementation must preserve old repositories and runs without a Profile version bump, must not add identity authentication, and must never broaden filesystem discovery beyond an explicitly bound worktree.

## Decision summary and active design dimensions

1. Add an opt-in review gate to generic transactions. A run is gated only when its caller supplies one or more review reasons; risk alone does not silently gate non-Query workflows.
2. Add `freeze_run` to validate and freeze a staged candidate, record a content-bound review candidate, and advance `PLANNED → REVIEW_REQUIRED` without changing live Wiki bytes.
3. Require the displayed candidate digest when applying a `REVIEW_REQUIRED` run. The digest proves byte/evidence identity, not human identity.
4. Keep low-risk direct Apply and post-Apply Review unchanged.
5. Introduce one `code_sources` module that owns Git identity normalization, portable code-source registry, private worktree bindings, exact resolution, and legacy-run rebuild.
6. Store portable snapshot identity in `.ad-wiki/code-source-registry.json`; store machine-local paths below `.ad-wiki/cache/code-worktrees/`, protected by an internal `*` gitignore and excluded from delivery.
7. Update portable registry transactionally after a Code Wiki run validates. Existing repositories gain it lazily or through an explicit deterministic rebuild command.
8. Implement multi-turn candidate discovery and natural-language staging intent in Query/Maintainer contracts, not as a new user-visible Skill and not as persistent query history.

The active design dimensions are transaction lifecycle, CLI/API compatibility, durable control metadata, migration, filesystem trust, and agent behavior.

## Proposed structure and responsibilities

### `scripts/ad_wiki/runtime.py`

Owns generic write transaction lifecycle.

- Extend `prepare_run` with optional `review_reasons` and normalized `evidence_bindings`.
- Accept a bounded deterministic `impact_summary` for gated Writeback and bind it into the frozen candidate.
- Add `freeze_run`.
- Extend `apply_run` with optional `candidate_digest`.
- Preserve `review_run` as post-Apply audit only.
- Keep `write_run_report.py` as a legacy low-level recorder, but forbid it from emitting approval/review-gate states or overwriting transaction-owned runs.
- Add `.ad-wiki/code-source-registry.json` to the protected baseline. For Code Wiki Apply, include it in the rollback snapshot and update it before final validation.

### `scripts/ad_wiki/code_sources.py`

New deep module owning all code-source identity and local resolution policy:

- safe Git remote normalization and repository inspection;
- repository-key derivation;
- portable registry load, validation, deterministic merge, and rebuild;
- private binding load, validation, and atomic update;
- exact worktree resolution with per-operation clean/revision requirements;
- registration of a successfully validated Code Wiki snapshot.

`code_wiki.py` imports and re-exports `inspect_code_repository` for source compatibility. `code_index/cache.py` imports the shared repository-key helper instead of retaining a second identity implementation.

### `scripts/ad_wiki/locking.py`

Owns the existing `.ad-wiki/lock` writer exclusion as one internal context manager. Runtime Apply, portable registry rebuild, and private binding read/merge/write use this same seam. A collision fails visibly and leaves state unchanged; callers retry rather than silently last-writer-wins.

### CLI wrappers

- `freeze_run.py` — freeze one staged gated run and return its review candidate.
- `bind_code_worktree.py` — explicitly validate and store one host-local association.
- `resolve_code_worktree.py` — read-only exact lookup and Git revalidation.
- `rebuild_code_source_registry.py` — deterministically rebuild portable entries from validated historical Code Wiki runs.

The repository's one-command/one-script convention is retained. Doctor and packaging tests enumerate the new commands.

### Skills and portable Query contract

- `ad-wiki-query` owns one ephemeral current candidate per conversational topic. New evidence replaces or invalidates the prior candidate. It surfaces a candidate once only when the Product Contract's convergence criteria hold.
- When a Concept/Source Summary declares exact code identity, Query calls the read-only resolver first; missing/ambiguous results ask for the exact worktree and never trigger scanning.
- Natural-language `准备写回`, `writeback`, or equivalent staging intent routes to Maintainer; Query itself creates no run or file.
- `ad-wiki-maintainer` maps a Query handoff to review reasons, prepares/stages/freezes a gated run, emits the required review packet and stops. A later explicit `apply` resumes the exact run and supplies its candidate digest.
- The generated repository `AGENTS.md` receives the same read-only candidate/staging boundary so hosts without the installed Query Skill do not regress.
- No new Writeback Skill is created. Delivered standalone read-only Wiki Skills remain non-writing and keep their current contract.

## Interfaces and data/control flow

### Generic transaction API

```python
prepare_run(
    repo,
    *,
    run_id,
    operation,
    risk,
    inputs,
    read_set,
    write_set,
    review_reasons=(),
    evidence_bindings=(),
    impact_summary=(),
) -> dict

freeze_run(repo, *, run_id) -> dict

apply_run(repo, *, run_id, candidate_digest=None) -> dict
```

CLI additions:

```text
prepare_run.py ... [--review-reason multi-turn|medium-risk|high-risk|explicit]...
                     [--evidence-json <object>]...
                     [--impact-json <object>]...
freeze_run.py --repo <wiki> --run-id <id> --json
apply_run.py --repo <wiki> --run-id <id> [--candidate-digest <sha256>] --json
```

Evidence binding v1 is a bounded discriminated object:

```json
{"kind":"raw","source_id":"SRC-...","sha256":"<64 hex>"}
{"kind":"code","source_id":"CODE-...","canonical_remote":"ssh://host/org/repo","revision":"<40 hex>"}
```

Rules:

- no absolute/local paths, credentials, query strings, fragments, or unknown fields;
- at most 64 bindings per run and bounded string lengths;
- sorted/deduplicated canonical storage;
- Raw bindings must match the repository's Raw registry; code bindings use safe normalized remote plus full commit SHA.

Impact summary v1 is a bounded sorted list rendered directly by Maintainer:

```json
{"path":"wiki/concepts/example.md","change":"changed","summary":"Clarifies startup versus readiness."}
```

`path` must be in the exact write set, `change` is `added | changed | weakened | removed`, and `summary` is a bounded single-line statement. A review-gated Writeback requires at least one impact entry. Maintainer may add presentation around it but must not substitute different impact conclusions without creating a new frozen candidate.

### Review candidate v1

`freeze_run` stores:

```json
{
  "review_candidate": {
    "schema_version": "1",
    "frozen_at": "...",
    "review_reasons": ["multi-turn", "medium-risk"],
    "write_set": ["wiki/concepts/example.md"],
    "staged_hashes": {"wiki/concepts/example.md": "..."},
    "evidence_bindings": [],
    "impact_summary": [
      {"path": "wiki/concepts/example.md", "change": "changed", "summary": "Clarifies startup versus readiness."}
    ],
    "baseline": {"...": "..."},
    "candidate_digest": "<sha256>",
    "prevalidation": ["exact-write-set", "utf8", "baseline", "raw-guard"]
  }
}
```

The digest is SHA-256 over canonical JSON containing run identity, operation, risk, review reasons, exact write set, staged hashes, evidence bindings, frozen impact summary, source hashes, and baseline. Timestamps and non-authoritative presentation text are excluded.

`freeze_run` preconditions:

- run is `PLANNED`;
- at least one review reason exists;
- a gated Writeback has at least one valid impact-summary entry;
- staged files exactly match the planned write set and are UTF-8;
- baseline and Raw guard still pass.

On success it advances to `REVIEW_REQUIRED`. Repeating freeze without changes returns unchanged; changed content requires a new run rather than silently re-freezing an already reviewed candidate.

Every new generic transaction carries `transaction_schema_version: "2"`. Apply uses that lineage plus review state to fail closed if a frozen run loses or malforms both review payload fields; old reports without the marker retain the genuine legacy path. Review reason/risk invariants are validated at Prepare: `multi-turn` cannot be low, and `medium-risk`/`high-risk` labels must match the recorded risk.

Repeated Freeze and Apply compare every persisted `review_candidate` payload field with the reconstructed authoritative payload, not only the stored digest. Mutating nested impact/evidence/write/baseline fields therefore invalidates confirmation even when the top-level run facts are unchanged.

`apply_run` behavior:

- ungated `PLANNED`: current direct path; an unexpected digest is rejected;
- gated `PLANNED`: reject and instruct the caller to freeze;
- `REVIEW_REQUIRED`: require exact `candidate_digest`, recompute the digest from current run/staged facts, then run existing baseline/Raw/lock/apply/validate/rollback flow;
- any run carrying current `review_reasons` or `review_candidate` stays on the digest path even if its persisted state is changed to legacy `APPROVED`/`AUTO_APPROVED`;
- genuine legacy `APPROVED`/`AUTO_APPROVED` records without current gate markers retain their staged-hash compatibility checks and do not create new approvals.

The runtime does not persist the conversational utterance or actor. A digest mismatch is a content-integrity error, not an authorization failure.

### Review packet handoff

Runtime returns candidate identity, frozen impact/evidence summaries, and staged paths. A gated Writeback cannot freeze without at least one evidence binding. Maintainer renders the semantic presentation from those bound entries:

- affected pages;
- claims added, changed, weakened, or removed;
- document/code evidence and revisions;
- unresolved evidence gaps;
- honest prevalidation scope;
- repository-local clickable staged file paths;
- run ID and candidate digest needed by the later Apply.

### Portable code-source registry v1

```json
{
  "version": 1,
  "sources": [
    {
      "repository_key": "<16 hex>",
      "canonical_remote": "ssh://host/org/repo",
      "repository": "repo-name",
      "root_commits": ["<40 hex>"],
      "snapshots": [
        {
          "revision": "<40 hex>",
          "source_summary_path": "wiki/sources/code-repo-....md",
          "validated_run_id": "code-wiki-..."
        }
      ]
    }
  ]
}
```

Identity uses normalized canonical remote when safe; otherwise repository basename plus sorted root commits. Snapshots are unique by repository identity, revision, Source Summary path, and validated run. The schema is exact: unknown top-level, record, or snapshot fields fail validation. Repository names must be safe basenames, and rebuild derives the basename from a safe remote or fails closed rather than copying a legacy path. All paths are repository-relative and must stay inside the Bundle. The registry never contains a worktree path or nondeterministic timestamp.

### Private worktree bindings v1

Location:

```text
.ad-wiki/cache/code-worktrees/.gitignore   # "*\n"
.ad-wiki/cache/code-worktrees/bindings.json
```

The directory is mode `0700`; binding file is written atomically with mode `0600` where the platform supports it. Delivery already excludes `.ad-wiki/cache`.

```json
{
  "version": 1,
  "bindings": [
    {
      "repository_key": "<16 hex>",
      "canonical_remote": "ssh://host/org/repo",
      "repository": "repo-name",
      "root_commits": ["<40 hex>"],
      "path": "/host-local/worktree",
      "bound_at": "..."
    }
  ]
}
```

Multiple paths may bind to one repository identity. Resolution never chooses among multiple valid candidates implicitly. Code Wiki Prepare automatically records the explicitly supplied clean worktree after successful validation; Maintainer may call the same binding capability when the user supplies an exact path.

### Code worktree API

```python
inspect_code_repository(code_repo, *, require_clean=True) -> code_source
bind_code_worktree(wiki_repo, *, code_repo) -> binding
resolve_code_worktree(
    wiki_repo,
    *,
    canonical_remote=None,
    repository_key=None,
    revision=None,
    require_clean=False,
) -> resolution
rebuild_code_source_registry(wiki_repo) -> registry_result
```

Resolution reopens and validates every candidate path, rejects symlink roots, compares the freshly inspected repository basename, normalized remote, and sorted root commits with the stored binding, verifies the requested commit exists, and enforces clean state when requested. A revision-qualified lookup always returns `read_mode: git-object` plus `read_revision`; Query must use revision-qualified Git reads even when the commit equals current HEAD. An unqualified lookup returns `working-tree`. Resolution returns structured `resolved`, `missing`, or `ambiguous` results; it never scans directories, clones, checks cross-project memory, or mutates stale bindings during a read-only lookup.

Unsafe remotes containing embedded passwords/tokens, local absolute paths, query strings, or fragments are not stored as portable remotes; identity falls back to root commits. Local paths may appear only in the private binding store and direct local CLI response.

All code-source mutators and the resolver first require an initialized Wiki and supported Profile before acquiring a lock or creating state. Both portable/private schema loaders require `version` to be a non-Boolean integer exactly equal to `1`.

## State, failure, compatibility, migration, security, and operations

### State and recovery

```text
PLANNED (ungated) ───────────────→ APPLIED → VALIDATED
PLANNED (gated) → REVIEW_REQUIRED → APPLIED → VALIDATED
                         │
                         └─ digest/baseline/evidence drift → FAILED, create a new run
```

Freeze never changes live Wiki bytes. Apply retains atomic snapshot/rollback. Lock contention remains retryable and does not alter state. A failed integrity/baseline check records a failed run; the Skill creates a new run and new review packet instead of reusing stale confirmation.

### Compatibility and migration

This is an expand-only change:

- existing run reports without `review_reasons`, `evidence_bindings`, or `review_candidate` behave as ungated runs;
- existing `APPROVED`/`AUTO_APPROVED` and `approved_staged_hashes` remain readable but are never emitted by new flows;
- the legacy run reporter cannot emit approval/review-gate states and cannot overwrite reports owned by `prepare_run`/Code Wiki transactions;
- `review_run` semantics do not change;
- missing `.ad-wiki/code-source-registry.json` is valid for old repositories;
- Init creates an empty v1 portable registry for new repositories;
- a validated Code Wiki Apply creates/merges the registry transactionally when absent;
- Code Wiki publishes the portable snapshot only after Bundle/Raw validation and durable `VALIDATED` state; if interruption occurs before registry replacement, idempotent completed-Apply repair publishes it on retry. Post-Apply Review shares the writer lock and repairs any missing validated snapshot before advancing to approved/rejected final state;
- a later rejected post-Apply Review does not erase the durable snapshot: rebuild recognizes an actual persisted `VALIDATED` event even when final run status is `FAILED`, while pre-validation failures remain excluded;
- `rebuild_code_source_registry.py` provides explicit byte-deterministic, idempotent backfill from exact validated Code Wiki run reports and Source Summaries; it stores no wall-clock field and fails closed when required legacy identity is unsafe or incomplete;
- every present `run.json` must first satisfy a minimal historical-run envelope before classification; unreadable, invalid-JSON, JSON-valid malformed, or symlinked reports abort rebuild before replacement, preserving previous registry bytes rather than silently dropping evidence;
- no Profile version bump and no destructive contraction occur in this task.

Rollback is ordinary file rollback for the portable registry plus the existing Bundle snapshot. Rebuild is deterministic and idempotent; it never derives or invents local paths.

Portable registry rebuild holds the same repository writer lock as Apply for its complete run-scan/rebuild/write transaction. Private binding holds that lock across Git validation plus binding read/merge/write. Read-only resolution relies on atomic replacement and sees either the old or new complete binding set.

### Security and privacy

Assets are live Wiki bytes, user confirmation integrity, source provenance, local filesystem topology, and potentially credential-bearing Git remotes.

Threat controls:

- staged-byte substitution is detected by candidate digest recomputation;
- digest is explicitly not authentication or non-repudiation;
- arbitrary evidence JSON is schema/size bounded and cannot carry paths or unknown fields;
- portable registry accepts only safe remotes and repository-relative Bundle paths, with every lexical component checked before resolution so direct/dangling symlinks cannot redirect control or evidence files;
- local bindings are excluded from Git/Skill delivery, permission-restricted, and revalidated on each use;
- every lexical component of the private-cache path is checked for symlinks, and its internal `*` gitignore must match before any binding write;
- symlink roots, replaced Git roots, non-Git directories, wrong remotes, missing revisions, dirty repositories when cleanliness is required, and ambiguous candidates fail closed;
- wrong-typed/unknown portable registry fields and incomplete legacy run provenance become bounded `ADWikiError` results rather than Python exceptions;
- resolver performs no broad filesystem/network discovery;
- ordinary Query content and candidate drafts are not persisted.

No new telemetry is required. Existing structured CLI errors and run events provide sufficient local diagnosis without recording prompts or user identities.

## Alternatives and rejected approaches

### Skill-only gate

Rejected because it cannot mechanically bind later Apply to the exact reviewed bytes and would regress easily across hosts.

### Restore `approve_run` and repository owners

Rejected because the requirement is content integrity plus explicit conversational intent, not identity authentication. Restoring it would contradict the Product Contract and revive deprecated policy.

### Infer gating from `risk` alone

Rejected because the Product Contract limits the new gate to Query-derived flows. Explicit non-Query medium/high maintenance remains under its existing authority envelope.

### Put local path in run reports or Source Summaries

Rejected because it leaks machine topology, is not portable, and contaminates durable evidence.

### Scan historical runs or workspace on every lookup

Rejected as steady state because it repeats work and reintroduces fuzzy discovery. Historical run scanning is allowed only in the explicit deterministic registry rebuild.

### Add a user-visible Writeback Skill

Rejected because Query already owns candidate discovery and Maintainer owns mutation. A third Skill would duplicate responsibility and create routing ambiguity.

## Risks and verification approach

- **Wrong-path regression:** verify no path reaches portable registry, run report evidence, delivery payload, or logs.
- **Gate bypass:** property tests cover every accepted run state, required/missing/wrong digest, and direct low-risk compatibility.
- **Evidence drift:** tests change staged bytes, write set, evidence bindings, Raw hashes, and baseline independently after freeze.
- **Impact drift:** tests change the frozen claims-added/changed/weakened/removed representation and prove the prior digest no longer applies.
- **Legacy collision:** fixtures prove old approved runs still apply while new runs never emit old approval fields.
- **Registry divergence:** compare incremental registration with deterministic rebuild output.
- **Legacy privacy:** reject unknown portable fields and absolute/unsafe legacy repository names; prove rebuild output contains no host path.
- **Ambiguous worktrees:** resolver must return ambiguity with all valid candidates and no selection.
- **Agent noise:** static contract tests plus representative multi-turn/ordinary-hit/unfinished-evidence journeys verify one current candidate and no automatic staging.
- **Delivery privacy:** package tests prove `.ad-wiki/cache` remains absent and standalone Skill behavior remains read-only.

Required verification includes focused runtime/CLI/unit tests, full Python test suite, plugin doctor, deterministic build/sync, and release build if repository-native commands provide one. Human experiential acceptance is limited to confirming that staged links open the frozen files and that the two natural-language confirmations are understandable; absent human acceptance does not invalidate engineering correctness but remains an explicit delivery note.

## Scope deltas and specialist evidence

No product scope delta was introduced.

- Codebase design: one `code_sources` module centralizes a currently duplicated volatile identity boundary and keeps Runtime/Code Wiki callers shallow.
- API design: new parameters are optional; old callers and stored runs preserve behavior. New commands each own one coherent job.
- Migration: expand-only tolerant readers, deterministic optional backfill, no destructive phase or Profile bump.
- Security: local paths remain private cache state; unsafe remotes and ambiguous/mismatched worktrees fail closed; digest binding is not represented as authentication.

No separate ADR is warranted: the decisions are scoped to this feature, are fully explained here, and do not create an organization-wide protocol outside AD Wiki.

## Open technical decisions

None.
