# AD-Wiki OKF Profile

Use `wiki/` as the OKF v0.2 Knowledge Bundle root. Treat every Markdown file except `index.md` and `log.md` as a Concept.

Use the repository's `content_language` for generated human-readable titles, descriptions, sections, and answers. Supported values are `zh-CN` and `en`; a missing field means `zh-CN`. This language preference does not translate Raw, code, quotations, proper identifiers, OKF keys, source IDs, or paths.

## Identity and links

- Derive the Concept ID from the path relative to `wiki/`, without `.md`.
- Do not add a duplicate page ID.
- Use standard Markdown Bundle links such as `[Incremental compilation](/concepts/incremental-compilation.md)`.
- Do not use `[[wikilinks]]`; the AD-Wiki validator reports them as unsupported syntax.
- Preserve unknown frontmatter fields when editing.
- Treat a broken link as an AD-Wiki quality warning, not an OKF conformance failure.

## Frontmatter

Require a non-empty `type`. Prefer `title`, `description`, and `tags`. Use the following families when applicable:

```yaml
---
type: Concept
title: Incremental knowledge compilation
description: Compile new evidence into durable, maintained knowledge.
tags: [knowledge-management]
sources:
  - id: source-key
    resource: https://example.com/source
    title: Source title
    author: human:owner
generated:
  by: ad-wiki/1.6.0
  at: 2026-08-15T10:00:00Z
status: draft
stale_after: 2027-02-15
---
```

- Default Agent-created content to `status: draft`.
- Use only `draft`, `stable`, or `deprecated`.
- Update `generated.at` only for a meaningful content change.
- Never write `verified` without a real verification event.
- Treat `today >= stale_after` as stale.
- Do not persist `trust_score` or `trust_tier`; consumers derive trust from `verified`.

For `type: Source Summary`, use optional `coverage: full | partial`. Write `full` only after reading the complete registered source. A partial summary must use `coverage: partial` and describe the omitted sections or range under evidence and uncertainty; validation reports it as reviewable compilation debt.

## Claim attribution

Give a cited source a stable `sources[].id`, then reuse it as the Markdown footnote label:

```markdown
The Wiki compounds prior synthesis.[^llm-wiki]

[^llm-wiki]: Karpathy, LLM Wiki idea file.
```

Separate source statements, Wiki inference, current synthesis, and unknown or disputed claims in prose.

## Reserved files

- Allow `okf_version: "0.2"` frontmatter only in the Bundle-root `index.md`.
- Keep nested `index.md` files without frontmatter.
- Group `log.md` entries under `## YYYY-MM-DD` headings, newest first.
- Add new log entries without rewriting historical entries.

## Attested Computation

Keep each sanctioned computation in its own `type: Attested Computation` Concept. Let the Agent supply only declared parameter values. Keep the computation definition, Executor instructions, and deterministic Attester references in the Bundle. Keep per-run Receipts outside the Bundle.
