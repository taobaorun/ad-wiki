# Code Wiki Contract

## Purpose

Compile one complete AD Wiki against one explicit latest Git code repository. The base Wiki remains independently usable. Code Wiki adds implementation Companions and quality feedback without treating code as automatic correction of public documentation.

## Run identity and coverage

- Bind one Wiki root, one code root, one code commit SHA, and one run ID.
- Evaluate every base Concept in the prepared inventory.
- Exclude indexes, log, hidden/reserved pages, `wiki/implementations/**`, and Source Summaries tagged `code-wiki-source`.
- Give every inventory item exactly one terminal status:
  - `enriched`
  - `docs-only`
  - `no-code-match`
  - `needs-review`
  - `failed`
- `complete` requires no pending, needs-review, failed, or no-code-match results. Otherwise report `partial` with exact residuals.

## Evidence rules

- Treat documentation as the public contract and code as current implementation evidence.
- Bind all source statements to the prepared full commit SHA.
- Cite repository-relative file path and symbol; line numbers are optional navigation hints.
- Read tests as evidence of intended boundaries, but state that this workflow did not execute them.
- Use callers, configuration, and tests to corroborate implementation matches. Name similarity alone is insufficient.
- Do not infer design intent solely from code shape.
- Do not describe internal implementation as a stable public API.

### Optional structural evidence

With explicit `--structural-index`, the Plugin-owned Java/SOFA index supplies deterministic candidate nodes and edges. It is not Wiki truth.

- Query expansion tokens must come from the graph vocabulary.
- Preserve `query_tokens` and `matched_node_ids` in each checkpoint.
- Each structural code ref requires `symbol_id`, graph-backed relation, `EXTRACTED | INFERRED | AMBIGUOUS`, and exact source location.
- Read original source and tests before using graph evidence in a Companion.
- Bindings publish only after a validated Apply and drive later affected-Concept refresh.
- Missing uv/tree-sitter environment fails structural mode; it never silently becomes model-only inside the same run.

## Enriched page contract

An implementation Companion must include:

1. base Concept link and code snapshot scope;
2. public document contract summary;
3. current implementation principles and invariants;
4. Mermaid for mechanisms with at least three meaningful states, steps, or participants, or a brief reason no diagram is needed;
5. bounded exact source excerpts with revision/path/symbol labels;
6. key classes, methods, configuration, and callers;
7. related test source and the boundary it declares, explicitly not executed;
8. document-code relationship;
9. uncertainty, unread scope, and continued-reading paths;
10. claim-level source footnotes.

Use `wiki/implementations/<base-concept-id>.md`, `type: Concept`, and tags `code-wiki` plus `implementation`.

## Managed base link

Only this marker block is Code Wiki-owned in the base Concept:

```markdown
<!-- ad-code-wiki:start -->
## 实现原理

- [查看源码实现](/implementations/<base-concept-id>.md)
<!-- ad-code-wiki:end -->
```

Use `Implementation` / `View source implementation` for English Wikis. Preserve every other byte unless line-ending normalization is required by the existing transaction. Damaged or duplicate markers require `needs-review`.

## Code snapshot Source Summary

Create exactly one `wiki/sources/code-<repo-slug>-<shortsha>.md` per run:

- `type: Source Summary`
- tag `code-wiki-source`
- `coverage: partial`
- full commit SHA and normalized remote or `urn:git-snapshot:<sha>`
- actual files/symbol families read and material unread scope

Do not claim coverage of the full repository.

## Feedback boundary

Allowed feedback kinds:

- `knowledge-gap`
- `granularity`
- `alias`
- `broken-link`
- `implementation-only`
- `apparent-divergence`
- `confirmed-divergence`
- `suspected-wiki-error`

Persist and summarize feedback, but do not apply semantic repairs in the Code Wiki run. A separate authorized Writeback must rebuild context and stage its own exact diff.

## Trust and failure rules

- The code repository must stay clean and at the prepared commit through Finalize.
- Never execute code repository content.
- Reject symlink escapes, binary/generated/vendor inputs selected as core evidence, absolute local paths, and suspected credentials/secrets.
- Checkpoint progress under the run; do not mutate live Wiki before Finalize and Apply.
- Wiki/code drift requires a new run; never silently rebaseline.
- Apply only finalized exact staged bytes and preserve existing rollback behavior.
