# Workflow Contracts

## Contents

- [Shared write protocol](#shared-write-protocol)
- [Init](#init)
- [Ingest](#ingest)
- [Query](#query)
- [Writeback](#writeback)
- [Lint](#lint)
- [Migrate](#migrate)

## Shared write protocol

For every operation that can change knowledge:

1. Resolve the repository and configured roots.
2. Run preflight checks and Raw guard.
3. Read `wiki/index.md`, then only relevant Concepts and sources.
4. Produce a plan containing inputs, read set, write set, conflicts, risk, and required validation.
5. Obtain the approval required by the risk policy.
6. Apply the complete write set.
7. Rebuild indexes, update the current ISO-date log block, validate the Bundle, and rerun Raw guard.
8. Summarize the diff and remaining warnings.

Use `.ad-wiki/runs/<run-id>/run.json` for local operation state when a durable run record is useful. Do not put operation records or Attestation Receipts in `wiki/`.

## Init

Run:

```bash
python <plugin>/scripts/init_bundle.py --repo <repo> --domain <domain> --json
```

Confirm that `raw/`, `wiki/`, `.ad-wiki/`, `ad-wiki.yaml`, root `index.md`, and `log.md` exist. The command is idempotent only while generated files remain identical; it refuses to overwrite changed files.

## Ingest

1. Require the source to already exist under `raw/`.
2. Register it with a stable URL, URN, or other canonical locator.
3. Treat an unchanged locator and content hash as already processed.
4. Read the source, then locate affected Concepts.
5. Create a Source Summary and update existing entity, concept, synthesis, question, and contradiction pages as needed.
6. Classify new evidence as `strengthens`, `weakens`, `contextualizes`, `contradicts`, or `supersedes` in prose and links.

Default to one supervised source. A Source Summary alone is incomplete when the source affects existing knowledge.

## Query

Search indexes and Concepts first. Return to Raw only to verify evidence or fill a documented gap. Answer with citations, expose uncertainty, and do not mutate by default.

At the end, state whether the result is a writeback candidate and identify the proposed target Concept. Do not write it until write authority is clear.

## Writeback

Write back durable comparisons, analyses, decisions, reusable explanations, and knowledge gaps. Skip temporary status, formatting-only output, and duplicate summaries. Apply the shared write protocol.

## Lint

Run:

```bash
python <plugin>/scripts/validate_bundle.py --repo <repo> --json
```

Interpret results as:

- `OKF-E*`: OKF structure or reserved-file failure.
- `ADW-E*`: mandatory AD-Wiki profile or safety failure.
- `ADW-W*`: reviewable quality issue.
- `ADW-I*`: informational result.

Default to report-only. Fix deterministic formatting and indexes only when the user authorizes safe fixes. Never auto-resolve contradictions, deprecate Concepts, add human verification, or delete content.

## Migrate

Read `migration-policy.md`. Produce a complete migration plan, require pre-apply approval, preserve a recoverable Git boundary, execute deterministic changes, and validate the entire Bundle. Plugin installation or upgrade alone never migrates knowledge.
