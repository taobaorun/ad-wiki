# Technical Design: Deterministic ZIP Skill Delivery v1.8

Design identity: `ad-wiki-zip-delivery-v1.8-accepted`

Product Contract: `docs/product-specs/ad-wiki-zip-delivery.md`

Requirements covered: R-ZD1–R-ZD13

Authority: accepted by the user's explicit `ad-gallop` invocation immediately after the proposed `directory | zip | both` solution on 2026-08-24.

## Current behavior, constraints, and invariants

- AD Wiki `1.7.0` builds one validated Wiki into one immutable directory `<output-parent>/ad-<wiki-name>` through `build_wiki_skill(repo, output_parent, wiki_name)` and the `build_wiki_skill.py` CLI.
- `ad_wiki.delivery` already owns candidate construction, source closure, secret/path gates, deterministic payload/manifest identity, identical-target detection and atomic directory rename. ZIP must reuse this exact candidate rather than select or render knowledge again.
- Generated Skills are host-neutral, contain a complete Bundle plus registered Raw, and remain usable without command execution. Archive support must not alter generated Query behavior or delivery template v1.
- Existing callers omit a format argument and depend on directory output, `output`, `status`, artifact/manifest digests, counts, capabilities, warnings and no-overwrite behavior.
- Source Wiki bytes, `.ad-wiki/runs`, caches, locks, unregistered Raw, external code repositories, global Skill installations and remote systems remain outside every artifact.
- The implementation uses the Python standard library and must continue to support large Raw files without loading the complete Skill or ZIP payload into memory.

## Decision summary and active design dimensions

1. Extend the existing Python/CLI interface with one closed `directory | zip | both` format option. `directory` is the default and preserves the current observable result.
2. Keep the validated temporary Skill directory as the one canonical candidate for all formats. ZIP is produced only from that candidate after its manifest exists.
3. ZIP contains file entries beneath exactly one `ad-<wiki-name>/` prefix. No alternate manifest, archive metadata file, directory rewrite or format-specific Query template is introduced.
4. Use deterministic ZIP metadata: lexicographically sorted POSIX entry names, fixed `1980-01-01 00:00:00` DOS timestamp, Unix creator, normalized regular-file modes, empty per-entry/archive comments and extras, `ZIP_DEFLATED` at fixed compression level `9`.
5. Stream candidate bytes into `zipfile` entry writers. ZIP64 remains enabled for large files. Archive validation streams entries back and compares path, byte digest, size and executable mode to the candidate.
6. Keep `artifact_digest` and `manifest_sha256` format-independent. Return archive identity outside the archive as SHA-256 and size; the archive cannot safely include its own digest.
7. Preflight every requested final target before publishing. An identical target is reusable; a non-identical, symlink or non-regular target fails before any new target is published.
8. In `both`, publish a newly required ZIP before a newly required directory because rollback of the new regular file is bounded and safe. If the later directory rename fails, unlink only the ZIP created by this run. Pre-existing identical outputs are never removed.
9. Release as Plugin `1.8.0`; Profile `0.1`, OKF `0.2`, Source Registry v1, Artifact Manifest v1 and delivery template v1 remain unchanged.

Activated design dimensions: public Python/CLI interface, deterministic transport schema, multi-target failure/recovery, compatibility, filesystem trust boundary, package-size operability and release identity. No new module owner, durable data migration, remote dependency, concurrency service, UI or Agent behavior change is introduced.

## Proposed structure and responsibilities

No new runtime package is required:

```text
scripts/ad_wiki/delivery.py
  existing candidate/source/manifest owner
  + deterministic ZIP writer and validator
  + requested-target preflight and publication transaction

scripts/ad_wiki/cli.py
  + --format directory|zip|both

skills/ad-wiki-ship/SKILL.md
  + operator-facing format selection and result interpretation

tests/test_delivery.py / tests/test_cli.py / tests/test_packaging.py
  + format, reproducibility, recovery, real compatibility and 1.8 identity
```

The ZIP writer remains private to `ad_wiki.delivery`: there is one current consumer and its invariants depend on the delivery candidate. A generic archive abstraction or separate module would expose policy without a second real owner.

Dependency direction stays `build_wiki_skill.py → cli → delivery → validated candidate → optional ZIP`. Generated Skills do not import Plugin code and ZIP extraction is not part of Query.

## Public interfaces

### Python

```python
build_wiki_skill(
    repo,
    *,
    output_parent,
    wiki_name=None,
    output_format="directory",
) -> dict
```

- `output_format` must be exactly `directory`, `zip` or `both`; other values raise `ADWikiError`.
- Omitting it is byte- and behavior-compatible with `1.7.0` directory mode.

### CLI

```text
python3 <plugin-root>/scripts/build_wiki_skill.py \
  --repo <built-wiki> \
  --output <output-parent> \
  [--wiki-name <name>] \
  [--format directory|zip|both] \
  --json
```

The default is `directory`. Existing exit codes remain: `0` for created/unchanged and `2` for invalid input, unsafe content, conflict or publication failure.

### Result

Existing top-level fields stay present. Add:

```json
{
  "format": "directory | zip | both",
  "status": "created | unchanged",
  "output": "/primary/output/path",
  "directory": null,
  "archive": {
    "status": "created | unchanged",
    "path": "/output/ad-sofa-wiki.zip",
    "sha256": "...",
    "size": 0
  }
}
```

- `directory` is `{status, path}` when requested, otherwise `null`.
- `archive` is `{status, path, sha256, size}` when requested, otherwise `null`.
- `output` remains the directory path for `directory` and `both`; in `zip` it is the ZIP path.
- Aggregate `status` is `created` when at least one requested output was created, otherwise `unchanged`.
- Existing `artifact_digest`, `manifest_sha256`, counts, capabilities, exclusions and warnings describe the uncompressed Skill candidate and are identical across formats for the same source/options.

## Deterministic ZIP contract

For a Skill `ad-sofa-wiki`, every archive name is:

```text
ad-sofa-wiki/<candidate-relative-posix-path>
```

Only regular candidate files are archived; the candidate builder already rejects symlinks and special files. Entries are sorted by candidate-relative POSIX path. Directory entries are omitted because all required directories are recreated by file paths and have no manifest identity or special permission contract.

Each file entry uses:

- timestamp `(1980, 1, 1, 0, 0, 0)`;
- `create_system = 3` (Unix);
- external mode `(S_IFREG | 0755) << 16` for executable helper entrypoints, otherwise `(S_IFREG | 0644) << 16`;
- `ZIP_DEFLATED`, compression level `9`;
- empty `extra` and `comment`, no archive comment;
- UTF-8 name behavior owned by `zipfile` when a path requires it;
- ZIP64 enabled and streaming copy in 1 MiB chunks.

The builder reopens the completed temporary ZIP before publication and requires:

- entry names equal the exact sorted expected list with one Skill prefix;
- no duplicate, absolute, backslash, empty, `.` or `..` component;
- every entry is a regular file with expected normalized mode;
- uncompressed size, SHA-256 and bytes match the candidate;
- CRC validation succeeds and there are no extra entries.

Archive SHA-256 and byte size are calculated only after close/validation. They are returned in the result and never interpolated into candidate files.

## Build and publication flow

```text
validate source / build private directory candidate / manifest
  → if zip requested: stream deterministic temporary ZIP from candidate
  → validate temporary ZIP and calculate archive identity
  → recheck source snapshot
  → preflight every requested final target
       absent     → needs publish
       identical  → unchanged
       conflict   → fail, publish nothing
  → publish required ZIP first
  → publish required directory second
       success → return aggregate result
       failure → unlink only ZIP newly published by this run, fail
  → cleanup all remaining private temporary paths
```

Directory identity uses the existing full tree digest/mode comparison. Archive identity uses full byte SHA-256 and size comparison; an existing archive must be a regular non-symlink file. Equality is never inferred from filename, mtime or embedded manifest alone.

In ZIP-only mode the private directory candidate is deleted after the ZIP is published. In directory-only mode no ZIP temporary file is created. In both mode a pre-existing identical directory or ZIP can be reused independently; rollback ownership records only newly published paths.

The output parent may be created as before. No final-looking target is created until all requested candidates and preflight checks pass.

## Failure, compatibility, security and operations

- A format error occurs before source or output mutation.
- A ZIP writer/validator failure leaves no final ZIP or directory and cleans its temporary file/directory.
- A conflicting requested target blocks `both` before either target changes.
- If a race changes a target after preflight, the existing no-overwrite rule remains authoritative; ordinary local filesystem rename limitations are reported as failure and bounded rollback runs only for this invocation's newly created ZIP.
- Rollback never removes a pre-existing identical artifact. Rollback failure is surfaced with both the publication and recovery path, not hidden as success.
- Archive entry paths are derived only from the already validated candidate and canonical Skill name; Wiki/Raw content cannot choose archive names or metadata.
- ZIP construction makes no network calls, runs no source content, follows no symlink, reads no file outside the candidate and writes only the explicit output parent.
- The standard library `zipfile`/`zlib` implementation is the only archive dependency. Determinism is asserted byte-for-byte in the supported CI/runtime environment and metadata is normalized across hosts.
- Existing generated directories and installed Skills are not mutated. Rollback for operators remains removing the newly produced ZIP or directory outside this command.

## Alternatives and rejected approaches

- **Make ZIP replace directory mode** — rejected because it breaks existing callers and local installation workflows.
- **Always emit both** — rejected because users may need only one transport and unnecessary outputs create conflict/cleanup burden.
- **Put the ZIP inside the Skill directory** — rejected because it changes artifact identity, creates self-packaging recursion and makes installation ambiguous.
- **Write archive SHA into Artifact Manifest** — rejected because the manifest is inside the ZIP and would create a digest self-reference; archive identity belongs in the builder result/distribution layer.
- **Archive the source Wiki repository directly** — rejected because it bypasses the validated allowlist and can include runs, caches, unregistered Raw or credentials.
- **Use `shutil.make_archive` or shell `zip`** — rejected because timestamp, mode, ordering, tool availability and extra metadata are not controlled tightly enough for R-ZD6.
- **Use `ZIP_STORED`** — deterministic but rejected because the user explicitly requested a compressed ZIP delivery format; fixed DEFLATE level provides the expected transport compression.
- **Publish the directory first in `both`** — rejected because rollback of a directory tree is broader and riskier than unlinking one newly created ZIP file.
- **Introduce a general archive plugin/interface** — rejected because v1.8 has one ZIP format and one caller; tar/encryption/signing are explicit non-goals.

## Risks and verification approach

- **ZIP nondeterminism:** build twice across output roots and delayed wall-clock time; compare complete ZIP bytes/SHA, entry metadata and manifest/artifact identity.
- **ZIP-slip or metadata leak:** inspect every entry for prefix/path/mode/time/extra/comment/create-system invariants; extract into an isolated directory and run the Skill validator.
- **Content divergence:** compare every extracted file byte/mode to directory mode and recompute manifest payload identities.
- **Partial `both` output:** inject archive publication and directory publication failures; prove no new single-sided result and preservation of pre-existing identical outputs.
- **Compatibility regression:** run every existing delivery/CLI/package test with omitted format and assert result/output behavior remains valid.
- **Scale/memory:** use streaming archive writes/reads and build real `sofa-wiki`; inspect time, size, counts and source byte identity.
- **Security regression:** reuse all source closure, secret, path, symlink and output conflict tests in ZIP modes; inspect archive for excluded paths and absolute machine strings.
- **Host validity:** validate directory mode, extracted ZIP and both-mode directory through the canonical Skill validator; validate both Plugin hosts and `ad-wiki-ship` discovery.

No ADR is proposed: deterministic ZIP is a task-local transport choice behind the existing delivery boundary, additive and reversible before another format consumer exists.

## Scope deltas and specialist evidence

- Target Plugin version is `1.8.0`, an additive SemVer minor. No knowledge schema or Query template migration is authorized.
- The request authorizes ZIP file creation only inside the explicit output parent and Git/PR publication through `ad-gallop`; it does not authorize publishing generated ZIPs to GitHub Releases or another external distribution system.
- Current `.agents/skills/`, `.claude/`, existing tags/releases and earlier delivery branch are run context and remain excluded.

## Open technical decisions

None.
