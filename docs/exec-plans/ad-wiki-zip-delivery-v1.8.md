# Implementation Plan: Deterministic ZIP Skill Delivery v1.8

Product Contract: `docs/product-specs/ad-wiki-zip-delivery.md`

Technical Design: `docs/designs/ad-wiki-zip-delivery-v1.8.md`

Requirements: R-ZD1–R-ZD13

Commit policy / authority: `delivery-only`; the explicit `ad-gallop` invocation authorizes scoped commits, push, one PR and convergence to merge-ready, but not merge or GitHub Release publication.

## Implementation decisions

- Extend the existing `ad_wiki.delivery` deep module; add no generic archive module or third-party dependency.
- Keep `output_format="directory"` as the Python default and `--format directory` as the CLI default.
- Build one validated directory candidate, then optionally derive and validate one deterministic ZIP from it.
- Use fixed ZIP metadata and streaming standard-library I/O. Keep archive identity outside Artifact Manifest v1.
- Preflight all requested targets, publish ZIP before directory in `both`, and roll back only a ZIP newly created by the current invocation if later publication fails.
- Release the additive public format option as Plugin `1.8.0`; preserve Profile/OKF/Registry/Manifest/template schema versions.

## Scope deltas

- The user explicitly adds ZIP transport and accepts `directory | zip | both`; no other compression, signing, upload, install or deployment behavior is authorized.
- Existing local Skill links, prior tags/releases, previous branch history and temporary real-Wiki output directories are excluded from commits.

## Implementation units

### U1 — Format interface and directory compatibility

- Requirements: R-ZD1, R-ZD2, R-ZD11.
- Dependencies and accepted-design pointers: TechnicalDesign Public interfaces.
- Affected modules and mutation: delivery API argument/result, CLI `--format`, focused existing/default/invalid-format tests.
- Entry / exit conditions: enter with `1.7.0` tests green; exit when omitted/default directory behavior remains compatible and all format values have an executable contract.
- Focused verification: Python/CLI default regression, invalid value structured error, result shape assertions.
- Recovery checkpoint: one additive parameter/CLI flag; no ZIP implementation is exposed until U2.

### U2 — Deterministic ZIP candidate and validation

- Requirements: R-ZD3, R-ZD5–R-ZD8, R-ZD12.
- Dependencies and accepted-design pointers: U1; Deterministic ZIP contract.
- Affected modules and mutation: private streaming ZIP writer/validator in `delivery.py`; ZIP-only tests and extraction comparison.
- Entry / exit conditions: enter with stable candidate directory; exit when ZIP-only produces one top-level Skill, is byte-reproducible, contains exact candidate bytes/modes, reports SHA/size and leaves no final directory.
- Focused verification: two-output-root byte comparison, entry metadata/path negatives, unzip + Skill validation fixture, archive SHA recomputation, excluded-path inspection.
- Recovery checkpoint: temporary ZIP remains private and can be removed without changing directory mode.
- Complexity allowance: deterministic metadata and validator helpers are authorized by R-ZD5/R-ZD6; keep them private and ZIP-specific.

### U3 — Both-mode transaction and immutable conflicts

- Requirements: R-ZD4, R-ZD9, R-ZD10.
- Dependencies and accepted-design pointers: U2; Build/publication flow.
- Affected modules and mutation: requested-target preflight, per-output status, ZIP-first publication, bounded rollback and fault tests.
- Entry / exit conditions: enter with valid directory/ZIP candidates; exit when absent/identical/conflicting combinations are deterministic and injected second-publish failure leaves no current-run partial output.
- Focused verification: both created/unchanged, mixed existing-identical, directory conflict, ZIP conflict, second-rename failure and rollback ownership tests.
- Recovery checkpoint: pre-existing outputs remain byte-identical; current-run ZIP is the only rollback target.
- Complexity allowance: one local publication transaction is required by R-ZD10; no lock service or generalized transaction abstraction.

### U4 — Builder Skill, release identity and packaging

- Requirements: R-ZD1, R-ZD11–R-ZD13.
- Dependencies and accepted-design pointers: U1–U3.
- Affected modules and mutation: `ad-wiki-ship` instructions/UI text as needed, manifests/Runtime/templates/migration note/tests to `1.8.0`, CLI/package/doctor assertions.
- Entry / exit conditions: enter with builder behavior green; exit when both hosts discover the option, report it clearly and all release identities are `1.8.0` without schema/template migration.
- Focused verification: CLI journeys for three modes, Plugin/Skill validators, doctor, version grep and package tests.
- Recovery checkpoint: release/version changes are additive and revert with the ZIP feature.

### U5 — Real Wiki proof, final verification and delivery

- Requirements: all.
- Dependencies and accepted-design pointers: U1–U4 and design risks.
- Affected modules and mutation: convergent fixes/tests/docs only; Git/PR publication after verification/review.
- Entry / exit conditions: enter with fixture suite green; exit at a merge-ready PR without merging or publishing a release.
- Focused verification: full suite, Ruff, compileall, frozen lock, diff check, Plugin/four builder Skill validators, real `sofa-wiki` directory/zip/both builds, byte reproducibility, Raw identity, excluded-state inspection, extracted Skill validation and bounded fallback.
- Recovery checkpoint: scoped delivery commit(s) on `feat/ad-wiki-zip-delivery`; no force push unless a later rebase requires `--force-with-lease`.

## Verification contract

- Required engineering evidence: focused ZIP/delivery/CLI tests plus the complete repository suite; Ruff; compileall; `uv lock --check`; `git diff --check`; doctor; Codex/Claude Plugin validators; all four builder Skills and one extracted generated Skill validator.
- Required security evidence: exact ZIP entry prefix/path/mode/time/extra/comment checks; no symlinks/special paths/excluded state; existing secret/source/path gates remain effective; no source or code-repository mutation.
- Required compatibility evidence: omitted format returns current directory behavior/result; artifact and manifest identities match across formats; Profile/OKF/Registry/Manifest/template versions remain unchanged.
- Required recovery evidence: all target conflicts are pre-publication; injected second publication failure removes only the current-run ZIP and preserves pre-existing identical outputs.
- Required real journey: build `sofa-wiki` in ZIP and both modes outside both repositories, compare two ZIP bytes/SHA, extract and validate, prove 4 Raw files and 7 external code sources, run one registered Raw fallback and verify source tree byte identity.
- Human experience: no named human acceptance is required before merge-ready; downloading/uploading the ZIP to a real deployment server remains outside this feature and is not impersonated.

## Risks and recovery

- Deflate/metadata drift: fixed writer fields plus full byte and entry-metadata tests.
- Archive path vulnerability: candidate-derived prefix and post-build entry validator.
- Partial dual output: complete preflight, ZIP-first order and ownership-bounded rollback.
- Compatibility break: default argument/CLI and top-level result remain directory-compatible.
- Large Raw memory pressure: streaming ZIP writer/reader, ZIP64 and real SOFA build.
- Rebase conflict: fetch/rebase latest `origin/main`, preserve main behavior, compare final tree and use only `--force-with-lease` when rewrite is truly required.

## Definition of done

- Every R-ZD requirement is implemented with no archive-format or deployment scope expansion.
- Directory mode remains compatible; ZIP and both modes are deterministic, validated, immutable and recoverable.
- Full verification passes on the final tree; isolated review has no actionable finding or same-context fallback is explicitly reported if isolation is unavailable.
- Scoped commits are pushed and one PR is open, current with `main`, mergeable, and free of required CI/review failures; it is not merged and no GitHub Release is created.
