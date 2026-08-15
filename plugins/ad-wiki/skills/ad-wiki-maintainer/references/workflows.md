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
3. Search, then read only relevant Concepts and sources.
4. Run `prepare_run.py` with inputs, complete read set, complete write set, and risk.
5. Write proposed content only beneath `.ad-wiki/runs/<run-id>/staged/`, mirroring each target's repository-relative path.
6. Inspect the staged diff and obtain the approval required by the risk policy. Run `approve_run.py`; never invent a human actor.
7. Run `apply_run.py`. It exclusively owns live writes, the repository lock, baseline check, index/log maintenance, validation, Raw guard, and rollback.
8. Summarize applied paths and warnings. Run `review_run.py` only after the recorded actor actually reviews the semantic diff.

Use `.ad-wiki/runs/<run-id>/run.json` for local operation state when a durable run record is useful. Do not put operation records or Attestation Receipts in `wiki/`.

Example transaction:

```bash
python <plugin>/scripts/prepare_run.py \
  --repo <repo> --run-id <run-id> --operation ingest --risk medium \
  --input raw/inbox/source.md --read wiki/index.md \
  --write wiki/sources/source.md --write wiki/concepts/affected.md --json

# Write staged files beneath:
# .ad-wiki/runs/<run-id>/staged/wiki/sources/source.md
# .ad-wiki/runs/<run-id>/staged/wiki/concepts/affected.md

python <plugin>/scripts/approve_run.py \
  --repo <repo> --run-id <run-id> --by <real-actor> --json
python <plugin>/scripts/apply_run.py --repo <repo> --run-id <run-id> --json
```

Do not include `index.md` or `log.md` in the staged write set. Do not retry a `FAILED` run; create a new run after resolving the reported cause. A lock-contention error leaves an approved run retryable.

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
4. Search for related Concepts before reading the minimum relevant set.
5. Create a Source Summary and update existing entity, concept, synthesis, question, and contradiction pages as needed.
6. Classify new evidence as `strengthens`, `weakens`, `contextualizes`, `contradicts`, or `supersedes` in prose and links.

Default to one supervised source. A Source Summary alone is incomplete when the source affects existing knowledge.

## Query

Run:

```bash
python <plugin>/scripts/search_wiki.py --repo <repo> --query <terms> --limit 10 --json
```

Read the returned Concepts before Raw. Return to Raw only to verify evidence or fill a documented gap. Answer with citations, expose uncertainty, and do not mutate by default. Search is lexical candidate retrieval, not proof; verify important claims against Concept provenance.

At the end, state whether the result is a writeback candidate and identify the proposed target Concept. Do not write it until write authority is clear.

## Writeback

Write back durable comparisons, analyses, decisions, reusable explanations, and knowledge gaps. Skip temporary status, formatting-only output, and duplicate summaries. Apply the shared staged-write protocol as a separate operation from Query.

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

Configured `lint` severities are executable policy: `error` fails validation, `warning` remains reviewable, and `ignore` suppresses that finding family. Domain Concept types outside `domain.concept_types` remain visible as `ADW-W250` so OKF readers can still tolerate extensions.

## Migrate

Inspect the current target first:

```bash
python <plugin>/scripts/migrate_bundle.py --repo <repo> --target-profile 0.1 --json
```

`status: current` is a successful no-op. An unsupported source or target is a real stop: never invent a migration. When a later Plugin packages a deterministic path, read `migration-policy.md`, produce the complete migration write set, require high-risk pre-apply approval, preserve a recoverable Git boundary, execute it through the shared transaction, and validate the entire Bundle. Plugin installation or upgrade alone never migrates knowledge.
