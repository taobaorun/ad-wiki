# Technical Design: AD Wiki Read-Only Skill Delivery v1.7

Design identity: `ad-wiki-skill-delivery-v1.7-accepted`

Product Contract: `docs/product-specs/ad-wiki-skill-delivery.md`

Requirements covered: R-SD1–R-SD18

Authority: accepted by the user's explicit `ad-gallop` invocation on 2026-08-23.

## Current behavior, constraints, and invariants

- AD Wiki `1.6.0` distributes three canonical authoring/query Skills and a shared Plugin Runtime, but it does not turn one built Wiki into a standalone knowledge Skill.
- A built Wiki stores durable knowledge under configured `bundle_root`, registered Primary Sources under configured `raw_root`, source identity in `.ad-wiki/source-registry.json`, and construction/recovery state in `.ad-wiki/runs/` and cache directories.
- Normal Query is compiled-first, remains read-only, and must work for Agents without command execution. Registered Raw fallback is optional and bounded by Concept provenance and Source Registry.
- The real `sofa-wiki` is not a Git worktree, contains registered Yuque Raw plus external code-revision sources, and currently has validated run state that must not enter a deployment artifact.
- Existing Validator, Raw Guard, Query contract, secret patterns and Plugin packaging conventions are the authoritative reusable seams. Ship must not reimplement knowledge maintenance or weaken those invariants.
- Source Wiki bytes, code repositories, local Skills installation, worktrees, stashes, credentials and remote systems remain outside the generated artifact unless explicitly allowed by the Product Contract.

## Decision summary and active design dimensions

1. Add a fourth builder Skill, `ad-wiki-ship`, and one deep read-only build module, `ad_wiki.delivery`. Release target is additive Plugin `1.7.0`; Profile `0.1`, OKF `0.2`, Source Registry v1 and existing Wiki data do not migrate.
2. The public command is `build_wiki_skill.py`. It creates exactly one standard Skill directory `<output-parent>/ad-<wiki-name>` and does not create an archive in v1; an archive can later be a deterministic transport of the same directory.
3. Generated Skills are self-contained snapshots. They do not require AD Wiki Plugin installation, the source Wiki path, or a server. Optional helper code is standalone standard-library read-only code copied into the Skill.
4. Mirror the allowed repository subset beneath `references/repository/`, preserving original relative paths. This lets packaged configuration, local links, Source Registry and Raw paths retain their existing semantics without rewriting Wiki content.
5. Package the complete configured Bundle and every registered Raw path, but exclude every other source-repository path. Non-registry sources such as Git/code revision URLs remain explicit external Primary Sources in the Wiki and manifest; their repository bytes are not implicitly copied.
6. Generate the Skill from canonical versioned templates owned by `ad-wiki-ship`; never ask a model to rewrite Query instructions during delivery. Query flow, fallback rules, citations, read-only boundaries and host path resolution are byte-stable template content. Only explicit Wiki identity/configuration variables and packaged knowledge differ.
7. Generate a short Skill entry plus one query contract reference, rather than embedding the Wiki or all operational rules in `SKILL.md`. This preserves progressive disclosure and host discovery quality.
8. Build in a sibling temporary directory, validate the complete candidate, then atomically publish. Existing identical output returns `unchanged`; existing non-identical/non-empty output fails without overwrite.
9. Artifact identity is a deterministic payload digest over sorted payload path, byte digest, size and executable flag. The manifest is not part of its own payload digest; the builder result separately reports the manifest digest.
10. Ship-specific blockers are stricter than ordinary Lint warnings for deployability: invalid Bundle/Profile, Raw Guard violations, unsafe paths/symlinks, broken local Bundle links, missing index entries/static Query entry, unresolved registry-backed evidence and high-confidence credential findings all block publication. Stale/orphan/partial-coverage findings remain manifest warnings.
11. No Writeback, session recording, Tool/MCP submission, deployment or remote publication is added. A new Wiki revision is delivered by rebuilding a new immutable snapshot.

Activated design dimensions: module/API boundary, generated Skill interface, immutable artifact schema, atomic publication, compatibility, AI/Agent behavior, sensitive-data trust boundary, failure recovery and package-size operability. No database, remote dependency, background job, UI or migration is introduced.

## Proposed structure and responsibilities

### Builder Plugin

```text
skills/ad-wiki-ship/
├── SKILL.md                     # resolve input/output/name, call builder, inspect result
├── agents/openai.yaml           # host-neutral discovery metadata
└── assets/delivered-skill/
    ├── SKILL.md.tmpl            # canonical generated Query entry
    ├── openai.yaml.tmpl         # canonical generated UI metadata
    └── query-contract.md        # canonical generated Query contract

scripts/ad_wiki/delivery.py      # identity, allowlist, closure, scan, copy, manifest, atomic publish
scripts/ad_wiki/delivery_query.py# standalone read-only helper copied into generated Skills
scripts/ad_wiki/cli.py           # thin ship CLI adapter
scripts/build_wiki_skill.py      # root entrypoint
```

`ad_wiki.delivery` owns one coherent responsibility: convert a validated AD Wiki snapshot into a standalone read-only Skill. Validator, Runtime, Code Wiki and Health remain unchanged owners; they are inputs, not dependencies of the generated Skill.

### Generated Skill

```text
ad-<wiki-name>/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── query_registered_raw.py
│   └── delivery_query.py
└── references/
    ├── query-contract.md
    ├── artifact-manifest.json
    └── repository/
        ├── ad-wiki.yaml
        ├── AGENTS.md
        ├── CLAUDE.md                 # only when canonical source entry exists
        ├── .ad-wiki/
        │   ├── source-registry.json
        │   └── domain.md             # optional existing read-only metadata
        ├── <bundle_root>/...         # complete regular-file Bundle snapshot
        └── <registered Raw paths>    # exact bytes for every registry record
```

The generated Skill contains no generic Maintainer/Code Wiki Runtime. `delivery_query.py` is a deliberately narrow standalone standard-library module: resolve the packaged repository root, validate config/Concept/source paths, verify selected Raw bytes against the packaged Registry, and return bounded excerpts. It exposes no writes, network calls, process execution or dynamic import.

Dependency direction is `build_wiki_skill.py → cli → delivery → existing validation/read-only primitives`. Generated `SKILL.md → packaged files/manual navigation`, with optional `query_registered_raw.py → delivery_query.py`. Nothing in the generated Skill imports the source Plugin.

## Canonical delivery templates

`ad-wiki-ship` owns one template version for every generated Skill. Delivery performs strict placeholder substitution; no LLM generation, summarization or prompt rewriting participates.

Stable template content includes:

1. resolve the installed Skill root rather than current working directory;
2. read packaged manifest, `ad-wiki.yaml` and Bundle-root index;
3. follow directory indexes/Markdown links and read complete relevant Concepts;
4. answer a compiled hit without inspecting Raw;
5. for one narrow missing detail, use the packaged bounded helper when available or manually resolve exact Registry-backed Raw;
6. label exact external Primary Sources outside the packaged snapshot when local evidence is insufficient;
7. answer in `content_language` with packaged Concept paths and source IDs;
8. preserve conflicts, stale/partial evidence and uncertainty;
9. keep Query byte-read-only and forbid Writeback, maintenance, deployment, logging and mutation.

Only these values vary between delivered Skills:

- `skill_name` and `wiki_name`;
- a bounded display label derived from the explicit Wiki identity;
- configured `content_language`, `bundle_root`, `raw_root` and domain name;
- artifact manifest identity/counts/digests/external-source inventory;
- packaged Wiki, Raw, Registry and optional domain metadata bytes.

The generated description follows one fixed shape and length budget so host discovery remains predictable. Wiki content, Raw text, Concept summaries and model-written prose are never interpolated into frontmatter or executable instructions. Unknown/missing placeholders fail the build. Manifest `built_with.delivery_template_version` records the canonical template revision.

Changing Query behavior requires updating the canonical template version in the AD Wiki Plugin and rebuilding the delivered Skill. Rebuilding the same Wiki with the same template version and options produces the same generated instructions.

## Public builder interface

### Python

```python
build_wiki_skill(
    repo,
    *,
    output_parent,
    wiki_name=None,
) -> dict
```

- `repo`: one explicit initialized AD Wiki root; symlink roots are rejected.
- `output_parent`: explicit local directory outside `repo`; target is `<output_parent>/<skill_name>`.
- `wiki_name`: optional explicit identity. When absent, use `repo.name` and report `name_source: repository-basename`.

### CLI

```text
python3 <plugin-root>/scripts/build_wiki_skill.py \
  --repo <built-wiki> \
  --output <output-parent> \
  [--wiki-name <name>] \
  --json
```

Exit behavior follows existing CLI conventions:

- `0`: `created` or byte-identical `unchanged` artifact;
- `2`: invalid input, unsafe/dirty closure, sensitive finding, output conflict or publication failure;
- no exit code represents partial success.

Success result:

```json
{
  "status": "created | unchanged",
  "skill_name": "ad-sofa-wiki",
  "wiki_name": "sofa-wiki",
  "name_source": "explicit | repository-basename",
  "output": "/explicit/builder/output/ad-sofa-wiki",
  "artifact_digest": "sha256",
  "manifest_sha256": "sha256",
  "counts": {
    "files": 0,
    "concepts": 0,
    "registered_sources": 0,
    "raw_files": 0,
    "external_sources": 0
  },
  "capabilities": {
    "compiled_query": true,
    "manual_raw_fallback": true,
    "helper_raw_fallback": true,
    "writeback": false
  },
  "warnings": [],
  "excluded": [".ad-wiki/runs", ".ad-wiki/cache", ".ad-wiki/lock"]
}
```

The builder may return an absolute output path because this result is local operator feedback. No absolute source/output path is written inside the Skill.

## Naming contract

Input names accept ASCII letters, digits, spaces, `_` and `-`. Canonicalization lowercases and converts each separator run to one `-`, then prefixes `ad-`. Other characters, empty results, a final name over 63 characters, or a target collision fail. The builder never derives identity from domain prose and never adds random suffixes.

Examples:

```text
sofa-wiki   → ad-sofa-wiki
SOFA Wiki   → ad-sofa-wiki
sofa_wiki   → ad-sofa-wiki
ad/sofa     → error
```

`ad-ad-wiki` is valid when the explicit Wiki name itself is `ad-wiki`; the prefix rule is literal and is not silently special-cased.

## Artifact Manifest v1

`references/artifact-manifest.json` is canonical JSON with sorted keys and deterministic array ordering:

```json
{
  "schema_version": "1",
  "skill_name": "ad-sofa-wiki",
  "wiki_name": "sofa-wiki",
  "built_with": {
    "plugin_version": "1.7.0",
    "delivery_template_version": "1",
    "profile_version": "0.1",
    "okf_version": "0.2"
  },
  "source": {
    "git_revision": null,
    "bundle_root": "wiki",
    "raw_root": "raw",
    "bundle_digest": "sha256",
    "source_registry_digest": "sha256"
  },
  "capabilities": {
    "compiled_query": true,
    "manual_raw_fallback": true,
    "helper_raw_fallback": true,
    "writeback": false,
    "maintenance": false,
    "deployment": false
  },
  "counts": {
    "files": 0,
    "concepts": 0,
    "registered_sources": 0,
    "raw_files": 0,
    "external_sources": 0
  },
  "external_sources": [
    {"resource": "git-or-url", "source_ids": ["id"], "concepts": ["concept-id"]}
  ],
  "warnings": [],
  "excluded": [".ad-wiki/runs", ".ad-wiki/cache", ".ad-wiki/lock"],
  "payload": [
    {"path": "SKILL.md", "sha256": "...", "size": 0, "executable": false, "kind": "skill"}
  ],
  "artifact_digest": "sha256-of-canonical-payload-identities"
}
```

Payload includes every generated/copied file except the manifest itself. `artifact_digest` hashes canonical JSON of payload entries; `manifest_sha256` is returned by the builder and can be recomputed independently. Build time, source/output absolute paths, OS user and machine metadata are absent.

`counts.files` is the number of payload entries plus the manifest itself. `bundle_digest` hashes canonical sorted entries of Bundle-relative path, byte digest and size; `source_registry_digest` is the SHA-256 of the exact packaged registry bytes. When the source root is an exact clean Git worktree, `git_revision` is HEAD; otherwise it is `null` with a warning rather than a misleading revision claim.

Registry-backed resources are packaged and counted as local evidence. Bundle source entries that do not match a registry canonical locator—particularly immutable Git/code revision URLs—are preserved as external sources and listed in the manifest. Ship never clones or copies a source-code repository implicitly; Code Wiki Companions remain the packaged compiled explanation and the exact upstream revision stays visible.

A source entry resolves to registered local evidence when its resource equals a registry `canonical_locator`, when its resource resolves to the registered repo-relative Raw path from the declaring Concept, or when its source ID equals the registry `source_id`. Every such resolution must identify exactly one record; ambiguous matches fail. Other resources remain external.

## Generated Query behavior

The generated `SKILL.md` is concise and domain-specific:

- description triggers on factual, explanatory, comparative, troubleshooting and procedural questions in the packaged Wiki domain;
- resolve all files relative to the installed Skill directory, never the current working directory or original Wiki path;
- read packaged `ad-wiki.yaml` and Bundle indexes, then full relevant Concepts;
- ordinary compiled hit does not read Raw;
- for one narrow missing detail, prefer the packaged helper when executable; otherwise manually map an exact Concept resource through the packaged Registry and inspect one relevant Raw document/section;
- if local evidence is insufficient/freshness-sensitive, use an exact declared external source when host capabilities permit and label it outside the packaged snapshot;
- answer in `content_language` with packaged Concept path and source IDs;
- never write the Skill, emit writeback candidates, call maintenance/build/deployment tools or record Query history.

The helper returns only structured bounded excerpts and integrity metadata. It never modifies access times intentionally, writes caches, creates logs or fetches external content.

## Build data/control flow

```text
explicit repo/output/name
  → resolve roots and canonical Skill name
  → validate Bundle/Profile/static entries
  → validate Source Registry + Raw Guard
  → calculate exact allowlist and registry/source closure
  → classify ship-blocking vs reviewable findings
  → stream secret/path scan + copy into sibling temporary Skill
  → render canonical versioned SKILL/UI templates and copy canonical query contract/helper
  → calculate payload identities + manifest
  → validate generated Skill, manifest and no-write/no-excluded-content invariants
  → compare existing target
     ├─ identical digest → unchanged, delete temp
     ├─ conflicting target → fail, delete temp
     └─ absent target → atomic rename temp to target
```

The source Wiki is snapshotted logically at build start by recording deterministic identities for every allowed input. Each file is copied from the same bytes used for its digest/secret scan; after copy, source identity is rechecked before publication. Source drift causes failure and temporary cleanup.

## Deployability gates and warnings

Always block:

- Validator errors or unsupported Profile/OKF/config;
- missing/unsafe `AGENTS.md`, source registry, Bundle root/index or configured roots;
- Raw Guard violation, registry duplicate/malformed record or registered file outside `raw_root`;
- symlink/special-file/path escape in any included path;
- broken local Bundle link, missing index entry, unsupported Wiki link or claim citation without a declared source ID, regardless of repository warning severity;
- registry-backed Concept resource with absent packaged evidence;
- high-confidence private key/credential patterns or denied sensitive filenames/suffixes;
- source drift during build, manifest mismatch, non-identical target or atomic publication failure.

Package but report as warnings:

- stale or orphan Concepts;
- Source Summary `coverage: partial`;
- external non-registry source references such as code revisions;
- semantic Health metrics that are unavailable without an Assessment;
- lack of Git revision for a non-Git Wiki.

The builder reports only relative paths, finding categories and validation codes for sensitive blockers. It never prints matched secret text.

## Failure, compatibility, security, and operations

- Source Wiki and code repos are read-only. Output must resolve outside the source repository and may not be a symlink.
- Temporary build directories are siblings of the final target with mode `0700`; copied regular files normalize to `0644`, helper entrypoints to `0755`.
- File copying/hashing/scanning is streaming; v1 caps included files at 100,000 and path length at 1,024 bytes, but imposes no arbitrary total-byte limit. Counts exceeding bounds fail before publication.
- Text secret scanning covers UTF-8/ASCII content and chunk boundaries; binary content is checked by filename/suffix and copied exactly. Private-key headers and high-confidence credential assignments block.
- Raw/Wiki content is untrusted evidence and never influences build instructions, output paths or executable content.
- Generated helper code comes only from the Plugin release, not from source Wiki/Raw.
- No remote calls, credentials, telemetry, Query logging or central service participate.
- Existing Plugin APIs are unchanged; this is an additive command/Skill. Existing Wikis need no migration.
- Updating the Plugin does not mutate or replace already generated Skills. Rebuild explicitly to produce a new digest.
- Rollback is deleting the newly generated output directory; source Wiki remains unchanged. The builder itself never deletes a non-temporary artifact.

## Alternatives and rejected approaches

- **Copy the whole Wiki repository** — rejected because it leaks runs, caches, local setup, unrelated Raw and potential credentials while coupling Query to authoring layout.
- **Package only `wiki/`** — rejected because the user requires complete registered Raw fallback and provenance closure.
- **One giant generated `SKILL.md` containing all knowledge** — rejected because it defeats progressive disclosure, exceeds discovery/context budgets and loses file-level citations.
- **Ask an Agent to rewrite the generated Skill for each Wiki** — rejected because behavior, safety wording and trigger quality would drift between identical builds; Wiki-specific facts belong in packaged references, not generated instructions.
- **Generated Skill depends on installed `ad-wiki-query` or original repository** — rejected because the artifact would not be independently deployable and host-neutral.
- **Package the entire AD Wiki Runtime** — rejected because it exposes mutation commands and unnecessary dependencies; only a narrow standalone read-only helper is justified.
- **Require helper execution** — rejected because some target Agents only have file-reading capability.
- **Overwrite an existing Skill in place** — rejected because it destroys immutable snapshot identity and complicates rollback; identical output is a no-op, changed output requires a new target/version decision by the caller.
- **Include source-code repositories used by Code Wiki** — rejected because the user authorized complete registered Raw, not implicit code-repository redistribution; exact external revisions remain declared.
- **Add Writeback now** — rejected for v1 because it changes an immutable deployment snapshot into a distributed writable system and requires a separate intake/privacy contract.

## Risks and verification approach

- **Incomplete evidence closure:** fixtures cover multiple registry versions, duplicate locators, external code sources, missing/changed Raw and Concept citation mapping; real `sofa-wiki` must build with all four registered Yuque sources and external code revisions listed, not copied.
- **Sensitive redistribution:** high-confidence secret/private-key/filename fixtures prove fail-closed behavior without secret echo; generated artifact recursively inspected for excluded paths and absolute source strings.
- **Nondeterminism:** build twice in different output roots and compare artifact/manifest identities; file ordering, modes and generated text are deterministic.
- **Template drift:** generate two different Wiki fixtures with the same template version, normalize the declared variable fields, and prove the Query workflow/safety sections are identical; reject unknown placeholders and enforce description length/trigger tests.
- **Partial artifact:** injected failures at copy, manifest and pre-rename gates leave no final target and clean temporary siblings.
- **Source mutation/drift:** source Wiki byte inventory before/after is identical; injected mid-build source change fails before publish.
- **Host usability:** validate generated `ad-sofa-wiki` with Codex and Claude Skill validators; run fresh-agent compiled-hit and Raw-fallback journeys with and without command execution.
- **Compatibility:** full existing test suite, Plugin validators, doctor, Query/Maintainer/Code Wiki/Health journeys and version identity remain green.
- **Scale:** build the real `sofa-wiki`, prove `.ad-wiki/runs`/cache exclusion, inspect counts/size/digests and exercise representative SOFABoot questions from the generated Skill.

Security specialist conclusion: the design expands the distribution boundary of registered Raw but does not add remote access. Strict registry closure, secret/filename blockers, no-overwrite atomic output, relative-only reporting and no sensitive override are required for implementation; no unresolved security decision remains.

No ADR is proposed: the immutable generated-Skill approach is fully owned by this feature contract/design and remains additive/reversible before external consumers establish a compatibility burden.

## Scope deltas and specialist evidence

- Target Plugin version `1.7.0` is an additive SemVer minor release; Profile/OKF/Registry schemas remain unchanged.
- `ad-wiki-ship` is a builder Skill, while generated `ad-${wiki-name}` Skills are domain-specific read-only artifacts. The naming similarity does not grant deployment, Git publication or ad-harness shipping authority.
- Existing local `.agents/skills`, `.claude/skills`, stash and other worktrees are excluded from source allowlist and implementation scope.

## Open technical decisions

None.
