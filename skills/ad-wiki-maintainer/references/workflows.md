# Workflow Contracts

## Contents

- [Runtime path](#runtime-path)
- [Progressive Wiki navigation](#progressive-wiki-navigation)
- [Shared write protocol](#shared-write-protocol)
- [Init](#init)
- [Ingest](#ingest)
- [Writeback](#writeback)
- [Lint](#lint)
- [Migrate](#migrate)

## Runtime path

Resolve `<plugin>` from the installed Skill location, never from the knowledge repository working directory. Normalize the Skill directory's `parent.parent` and require `<plugin>/scripts/` plus the current host manifest before running packaged commands.

## Progressive Wiki navigation

The model owns semantic navigation. Read the configured Bundle-root `index.md`, follow relevant directory indexes, search only Bundle Markdown with `rg` or the host equivalent, and read full pages selected from those signals. Refine identifiers, terms, and synonyms when the first pass is insufficient. Do not route Wiki knowledge through a deterministic scorer, candidate catalog, hydration envelope, fixed Top-K, or pre-model character budget.

For example:

```bash
rg -n --glob '*.md' '生命周期|启动回调|ComponentLifeCycle' <repo>/<bundle-root>
```

Search matches navigate to evidence; they do not prove claims. Record every page actually read in the transaction's complete read set.

## Shared write protocol

For every operation that can change knowledge:

1. Resolve the repository and configured roots.
2. Run preflight validation and Raw guard.
3. Navigate the current Wiki directly and read the minimum complete impact set.
4. Run `prepare_run.py` with inputs, complete read set, complete write set, and risk.
5. Write proposed content only beneath `.ad-wiki/runs/<run-id>/staged/`, mirroring each target's repository-relative path.
6. Inspect the complete staged semantic diff. Check targets, claim attribution, coverage, uncertainty, and Markdown links before mutation.
7. Run `apply_run.py`. It exclusively owns live writes, the repository lock, baseline check, exact staged bytes, index/log maintenance, validation, Raw guard, and rollback.
8. Summarize usable results and remaining work. Run `review_run.py` only after the recorded actor actually reviews the semantic diff; Review is optional and never gates Apply.

Use `.ad-wiki/runs/<run-id>/run.json` for local operation state when a durable run record is useful. Do not put operation records or Attestation Receipts in `wiki/`.

```bash
python3 <plugin>/scripts/prepare_run.py \
  --repo <repo> --run-id <run-id> --operation ingest --risk medium \
  --input raw/inbox/source.md --read wiki/index.md \
  --write wiki/sources/source.md --write wiki/concepts/affected.md --json

# Write and inspect the complete staged files, then:
python3 <plugin>/scripts/apply_run.py --repo <repo> --run-id <run-id> --json
```

Do not include `index.md` or `log.md` in the staged write set. Do not retry a `FAILED` run; create a new run after resolving the reported cause. Lock contention leaves a planned run retryable.

## Init

```bash
python3 <plugin>/scripts/init_bundle.py \
  --repo <repo> --domain <whole-wiki-domain> --language zh-CN --json
```

`domain` names the whole long-lived Wiki, not the current import slice. `--language` accepts `zh-CN` and `en` and defaults to `zh-CN`. New repositories do not configure owners or a repository-local approval policy. A hidden legacy `--owner` argument is accepted for one compatibility release, ignored, and reported as deprecated.

Confirm that `raw/`, `wiki/`, `.ad-wiki/`, `ad-wiki.yaml`, root `index.md`, and `log.md` exist. Init refuses to overwrite changed files. A legacy repository without `content_language` behaves as `zh-CN` and is not rewritten merely to add it.

## Ingest

1. Require the source to already exist under `raw/` and register it with a stable locator.
2. Treat an unchanged locator and content hash as already processed.
3. Navigate the Wiki to identify related Concepts and conflicts.
4. Read the complete source. Set Source Summary `coverage: full` only then; otherwise use `coverage: partial` and describe the exact omitted range or sections.
5. Create a Source Summary and update every affected answer-bearing page. Classify new evidence as `strengthens`, `weakens`, `contextualizes`, `contradicts`, or `supersedes` in prose and links.
6. Use standard Markdown Bundle links such as `[Incremental compilation](/concepts/incremental-compilation.md)`. Never create `[[wikilinks]]` or links to absent pages.
7. Before calling the requested import complete, report full/partial sources and important registered sources not yet integrated into answer-bearing Concepts.

Default to one supervised source. A Source Summary alone is incomplete when the source affects existing knowledge.

## Writeback

Write back durable comparisons, analyses, decisions, reusable explanations, and knowledge gaps. Skip temporary status, formatting-only output, and duplicate summaries. Re-navigate the current Wiki to establish the impact set, then use the shared staged-write protocol as an independent maintenance operation.

## Lint

```bash
python3 <plugin>/scripts/validate_bundle.py --repo <repo> --json
```

- `OKF-E*`: OKF structure or reserved-file failure.
- `ADW-E*`: mandatory AD-Wiki profile or safety failure.
- `ADW-W*`: reviewable quality issue.
- `ADW-I*`: informational result.

Default to report-only. Translate findings into ordinary language for the user. Never auto-resolve contradictions, deprecate Concepts, add human verification, or delete content.

## Migrate

```bash
python3 <plugin>/scripts/migrate_bundle.py --repo <repo> --target-profile 0.1 --json
```

`status: current` is a successful no-op. An unsupported source or target is a real stop. A later packaged migration requires an explicit user request, a complete staged diff, a recoverable Git boundary, and full-Bundle validation. Plugin installation or upgrade alone never migrates knowledge.
