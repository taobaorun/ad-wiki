---
name: ad-wiki-ship
description: Build one validated AD Wiki into one self-contained read-only ad-${wiki-name} Skill directory, deterministic ZIP, or both for local delivery. Use after Wiki construction when the user wants a distributable knowledge Skill, not deployment or a multi-Wiki bundle.
---

# AD Wiki Ship

Build one standalone read-only Skill from one explicitly selected, already constructed AD Wiki. This operation creates a local directory, deterministic ZIP, or both; it does not deploy, upload, publish, install, or modify the source Wiki.

## Resolve the build

1. Require one explicit AD Wiki repository and one explicit output parent outside that repository.
2. Use an explicit Wiki name when supplied; otherwise use the repository basename. The builder deterministically creates `ad-${wiki-name}` and rejects unsafe or conflicting names.
3. Resolve the packaged command from this installed Skill, never from the source Wiki. In Claude Code use `${CLAUDE_SKILL_DIR}`. In Codex use the absolute directory containing this `SKILL.md`; normalize `<plugin-root>` as its `parent.parent`.
4. Run exactly one local build:

   ```bash
   python3 <plugin-root>/scripts/build_wiki_skill.py \
     --repo <built-wiki> --output <output-parent> \
     [--wiki-name <name>] [--format directory|zip|both] --json
   ```

   Select `directory`, `zip`, or `both`. Use `directory` when no format is specified, `zip` for only `ad-${wiki-name}.zip`, or `both` for the directory and ZIP together.

## Interpret the result

- `created` means one complete Skill was atomically published.
- `unchanged` means the existing target is byte-identical.
- The result identifies the requested format, per-output status/path, and archive SHA-256/size when ZIP is requested. `artifact_digest` still identifies the uncompressed Skill content.
- An invalid Wiki, unresolved registered source, unsafe path, suspected credential, changed source or non-identical target is a hard failure. Do not bypass the gate or overwrite the target.
- Report the generated Skill name, output, artifact digest, counts, read-only capabilities, exclusions and warnings in ordinary language.

The generated Skill uses canonical templates for Query workflow, citations, bounded registered-Raw fallback and immutable safety rules. Wiki-specific content stays under packaged references; delivery never asks a model to rewrite those instructions.

## Boundaries

- Include the complete Bundle, Source Registry and every registered Raw version; exclude unregistered Raw, runs, cache, locks and unrelated repository files.
- External code or URL sources remain declared provenance and are not cloned or copied.
- ZIP is only a deterministic transport of the same validated Skill candidate. Do not archive the source Wiki directly or add files outside the candidate.
- Do not add knowledge mutation, session capture, remote calls, credentials, deployment steps or Marketplace publication.
- Do not commit, push, open a PR, install the generated Skill or delete an existing artifact without separate user authority.
