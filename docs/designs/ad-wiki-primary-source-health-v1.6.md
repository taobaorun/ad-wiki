# Technical Design: AD Wiki Primary-Source Context and Health v1.6

Design identity: `ad-wiki-primary-source-health-v1.6-accepted`

Product Contract: `docs/product-specs/ad-wiki-primary-source-context.md`

Requirements covered: R-PSC1–R-PSC12, R-HM1–R-HM15

Authority: autonomous `ad-gallop` acceptance is valid because the Product Contract fixes every observable product choice and delegates reversible schema/layout/weight mechanics within explicit boundaries.

## Current behavior, constraints, and invariants

- Plugin `1.5.0` introduced optional structural Code Wiki; the current worktree contains an uncommitted `1.5.1` Query/Raw improvement that must be reconciled rather than treated as authority.
- `validate_repository()` owns OKF/Profile conformance and lint policy. It returns errors/warnings/info and must not silently become a product-health score.
- `query_registered_raw()` is read-only, provenance-bound and hash-verifying. Agents without command execution must remain able to use compiled Wiki and exact file-reading fallback.
- Structural graphs and bindings live under `.ad-wiki/cache/code-index/`, are local and rebuildable, and must not enter the Bundle.
- Query does not persist user questions, host memory or telemetry. Code repositories remain clean, read-only and unexecuted.
- Code Wiki continues to evaluate every base Concept; importance signals cannot remove inventory items.
- Profile `0.1`, OKF `0.2` and Source Registry v1 remain compatible. This release requires no Bundle migration.

## Decision summary and active design dimensions

1. Release as Plugin `1.6.0`: the new health-report contract and structure-quality workflow are additive product capability, not a patch-only correction.
2. Keep compiled-first Query. Runtime Raw fallback is preferred; exact manual registered-source reading and exact upstream source descent are Agent behaviors governed by the Query Skill/static contract, not hidden network behavior in deterministic Python.
3. Add one deep read-only module, `ad_wiki.health`, with public `inspect_wiki_health(...)`; expose it through `inspect_wiki_health.py` and `health_main`.
4. Keep validation and health separate. Health consumes validator/Raw/code-index facts but does not change lint severities, write indexes, build code graphs, fetch upstream sources or mutate operation state.
5. Split evidence into deterministic repository facts and an optional versioned semantic assessment. Semantic metrics never pretend to be deterministically inferred from headings or filenames.
6. Return metric vectors and `overall_status: healthy | unhealthy | incomplete`; never return an overall numeric score.
7. Add ToC/key-system, Glossary and health-assessment assets to the Maintainer workflow. They are reusable authoring structures, not new OKF types or mandatory root files.
8. Repair the minimal example to use the current Karpathy Gist locator while honestly declaring that the packaged Raw is a partial paraphrase.

Activated design dimensions: module/API boundary, AI/agent behavior, trust/security, compatibility, resource bounds and operability. No durable database, background lifecycle, concurrency or destructive migration is introduced.

## Proposed structure and responsibilities

```text
scripts/ad_wiki/health.py
  ├─ validate assessment/report schemas and limits
  ├─ collect deterministic Bundle/Raw/index facts
  ├─ collect optional Code Wiki graph/binding/Git facts
  ├─ calculate every R-HM metric or honest unavailable result
  └─ derive overall_status from applicable correctness gates

scripts/ad_wiki/core.py
  └─ remains OKF/Profile validator and static Agent contract owner

scripts/ad_wiki/code_wiki.py + code_index/
  └─ remain Code Wiki lifecycle/graph owners; health only reads public artifacts

scripts/ad_wiki/cli.py
  └─ thin argument/error/exit adapter for inspect_wiki_health

skills/ad-wiki-maintainer/
  └─ owns model-generated semantic assessment, key-system/ToC and Glossary authoring guidance

skills/ad-wiki-query/
  └─ owns automatic compiled → local Primary Source → exact upstream evidence descent
```

The health module is justified by R-HM1–R-HM15: putting these policies in `core.py`, `runtime.py` and `code_wiki.py` would leak one responsibility across three owners and couple conformance validation to optional semantic evidence.

Dependency direction is `cli → health → core/code_wiki/code_index`. Existing modules do not import health.

## Public interfaces

### Python

```python
inspect_wiki_health(
    repo,
    *,
    assessment_path=None,
    code_repo=None,
    today=None,
) -> dict
```

- `repo` is one explicit initialized AD Wiki.
- `assessment_path`, when supplied, must resolve to a regular non-symlink JSON file inside `repo`, be at most 2 MiB and satisfy Assessment v1.
- `code_repo`, when supplied, must be a separate clean Git worktree. Health may inspect Git history and matching existing structural cache/bindings; it never builds an index, edits or executes the code repository.
- `today` makes stale calculations deterministic.

### CLI

```text
python3 <plugin-root>/scripts/inspect_wiki_health.py \
  --repo <wiki> \
  [--assessment <repo-relative-json>] \
  [--code-repo <clean-git-repo>] \
  [--today YYYY-MM-DD] \
  [--require-healthy] \
  --json
```

Valid reports exit zero unless `--require-healthy` is set and `overall_status != healthy`. Invalid arguments/artifacts exit 2 using the existing structured error contract. The command never writes a report file; callers may explicitly redirect output.

### Health Report v1

```json
{
  "schema_version": "1",
  "plugin_version": "1.6.0",
  "calculated_at": "ISO-8601",
  "repository": ".",
  "assessment_identity": {
    "wiki_revision": "git-sha-or-unborn",
    "wiki_digest": "sha256-of-current-bundle",
    "code_revision": null
  },
  "overall_status": "healthy | unhealthy | incomplete",
  "metrics": [
    {
      "metric_id": "source-integrity",
      "value": 1.0,
      "numerator": 3,
      "denominator": 3,
      "scope": {"kind": "wiki", "paths": [".ad-wiki/source-registry.json"]},
      "evidence": [{"kind": "validation", "code": "raw-guard", "paths": []}],
      "calculated_at": "ISO-8601",
      "status": "pass | warning | fail | unavailable",
      "unavailable_reason": null
    }
  ],
  "findings": [],
  "limits": []
}
```

Invariants:

- every metric ID occurs exactly once and metrics are sorted by ID;
- an available ratio has integer numerator/denominator and a value derived from them;
- `unavailable` requires null value/numerator/denominator, non-empty reason and evidence describing the missing input when possible;
- available metrics require non-empty evidence;
- no `overall_score` or equivalent field exists;
- findings contain only repo-relative paths/symbol IDs/question IDs, never absolute paths or source contents.

`overall_status` is `unhealthy` when an applicable R-HM2 gate fails, `incomplete` when an applicable gate cannot be evaluated, otherwise `healthy`. Code-specific gates become applicable when `--code-repo` is supplied or a validated Code Wiki run/binding exists. Semantic conflict/snapshot gates require Assessment v1, so a full health verdict without an assessment is intentionally `incomplete`.

### Semantic Assessment v1

The assessment is explicit, versioned, reviewable evidence generated during an authorized Maintainer/Lint exercise. It is not a Query log.

```json
{
  "schema_version": "1",
  "wiki_revision": "git-sha-or-unborn",
  "wiki_digest": "sha256-of-current-bundle",
  "code_revision": "optional-git-sha",
  "key_systems": [{
    "id": "stable-id",
    "evidence": ["wiki/concepts/example.md"],
    "concept_ids": ["concepts/example"],
    "dimensions": {
      "entry": true,
      "boundary": true,
      "mechanism": true,
      "dependencies": true,
      "primary_sources": true,
      "cross_links": true
    }
  }],
  "canonical_terms": [{
    "term": "canonical name",
    "evidence": ["wiki/concepts/example.md"],
    "defined": true,
    "consistent": true,
    "aliases": []
  }],
  "material_claims": [{
    "id": "claim-id",
    "concept_id": "concepts/example",
    "primary_source": true,
    "citation_depth": "root | document | section | code",
    "conflict": "none | visible | silent",
    "ambiguity": "none | visible | silent"
  }],
  "snapshot_consistent": true,
  "detected_conflicts": 0,
  "representative_questions": [{
    "id": "question-id",
    "outcome": "compiled-hit | source-descent | knowledge-gap | wrong-answer | wrong-navigation",
    "requires_descent": false,
    "descent_success": null,
    "asked_evidence_mode": false,
    "unrelated_source_access": false,
    "snapshot_disclosed": true,
    "wiki_assisted": {"steps": 1, "files": 2, "input_tokens": 1000, "time_ms": 500, "wrong_turns": 0},
    "baseline": {"steps": 3, "files": 8, "input_tokens": 5000, "time_ms": 2500, "wrong_turns": 1},
    "user_feedback": null
  }],
  "scale_points": [{"repository_size": 1000, "wiki_size": 10}],
  "feedback": []
}
```

Arrays are bounded to 10,000 items, aliases/evidence/paths to 100 per item and strings to 1,000 characters. Unknown keys are rejected so future meanings require a schema version. The assessment contains curated question IDs and aggregate journey measurements, not prompt text or transcripts.

## Metric data and control flow

```text
repo + optional assessment + optional clean code repo
  → validate repository/Raw integrity and exact inputs
  → collect deterministic facts
  → load validated Code Wiki run/graph/bindings when applicable
  → validate semantic assessment revision binding
  → calculate metric vector
  → validate report invariants
  → derive healthy | unhealthy | incomplete
  → emit only; no writes
```

Deterministic metrics:

- Source Integrity, Citation Validity, broken managed links, stale/orphan/index drift and Source-to-Concept Yield come from existing repository artifacts and validators.
- Code Wiki Concept Evaluation comes from the newest validated/reviewed Code Wiki run whose live Bundle/code revision still matches.
- Invalid Code References, active-code coverage and high-centrality/unbound proxies use matching existing graph/bindings plus optional clean Git history.

Assessment-backed metrics:

- key-system/ToC completeness, glossary, material-claim primary-source coverage/citation depth, conflict/ambiguity visibility, representative-question success, evidence descent, path compression, scale relationship and user usefulness.

Missing assessment/code/cohort evidence returns `unavailable`; the Runtime never invents semantic denominators.

## ToC, Glossary and Code Wiki behavior

- Maintainer templates provide ordinary `type: Concept` structures tagged `ad-wiki-key-system-inventory` and `ad-wiki-glossary`; they do not introduce OKF types or reserved filenames.
- Initial/full Wiki compilation creates or updates those Concepts when the domain evidence supports them. Incremental ingest updates them only when the new source changes systems or terminology.
- The model may use directory, graph, Git and available runtime signals to prepare the assessment and prioritize investigation. Every Code Wiki base Concept remains in the canonical inventory and receives a terminal status.
- Signals and weights are evidence attached to the assessment/report; no fixed relevance threshold removes Concepts.

## Failure, compatibility, migration, security, and operations

- Health inspection is side-effect free. Invalid inputs fail before metric calculation; individual missing evidence produces `unavailable`, not a fabricated zero.
- Existing `validate_bundle.py`, `doctor_plugin.py`, Init, Query, Maintainer and Code Wiki interfaces remain compatible.
- Profile/OKF/source-registry/code-index schemas do not change. Assessment/Health Report v1 are additive ephemeral interfaces; no migration command is added.
- Wiki, Raw, code, assessment and upstream content are untrusted evidence. No content is executed or treated as instructions.
- Assessment paths are repo-contained, regular, UTF-8 JSON and size-bounded; symlink/path escapes and unknown keys fail closed.
- Git inspection uses argument arrays, a bounded history window and repo-relative output. It never uses shell interpolation, checkout, fetch or code execution.
- No external network call occurs in health Runtime. Query Skill may use an exact Concept-declared upstream source through host capabilities and must label it outside the compiled snapshot.
- Reports never persist prompts, transcripts, credentials, absolute paths or source bodies. No central telemetry is introduced.

## Alternatives and rejected approaches

- **Extend `validate_repository()` with all health semantics** — rejected because conformance/lint is deterministic while several health metrics require reviewable semantic or experiential evidence; mixing them would make `ok` depend on unavailable model judgment.
- **Infer key systems/Glossary/material claims entirely from filenames and headings** — rejected as Context Poisoning: it would create precise-looking denominators without semantic authority.
- **Persist every report and query under `.ad-wiki/`** — rejected by privacy and no-Query-log requirements; explicit assessment/report files remain caller-owned.
- **One weighted health score** — rejected because high coverage could mask source-integrity, snapshot or citation failures.
- **Build/fetch code indexes or upstream docs during health inspection** — rejected because inspection must stay read-only, reproducible and capability-portable.
- **Make assessment mandatory for any output** — rejected because deterministic partial diagnostics are useful; missing semantic evidence is represented honestly as `incomplete`/`unavailable`.

## Risks and verification approach

- Schema complexity: property/negative tests cover unknown fields, limits, ratio invariants, unavailable semantics and deterministic ordering.
- False health: every gate and denominator has object-level evidence; unavailable semantic inputs force `incomplete`.
- Large repositories: bounded assessment, Git history and graph/file limits; comparable benchmark on fixtures and real SOFA Wiki when available.
- Privacy: tests prove reports omit question text, absolute paths, Raw contents and external credentials.
- Compatibility: the existing 103-test suite, Plugin/Skill validators and model-only/structural Code Wiki journeys remain green.
- Experience: replay the SOFABoot health-check question for automatic Primary Source descent and run health inspection both without assessment (`incomplete`) and with a version-bound fixture assessment (deterministic result).

No ADR is promoted: the report/assessment contracts are versioned within this feature and reversible before external adoption; the enduring product reasons already live in the Product Contract.

## Open technical decisions

None.
