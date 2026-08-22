# Implementation Plan: AD Wiki Read-Only Skill Delivery v1.7

Product Contract: `docs/product-specs/ad-wiki-skill-delivery.md`

Technical Design: `docs/designs/ad-wiki-skill-delivery-v1.7.md`

Requirements: R-SD1–R-SD18

Commit policy / authority: `delivery-only`; the explicit `ad-gallop` invocation authorizes scoped commits, push, one PR and convergence to merge-ready, but not merge.

## Implementation decisions

- Release the additive builder capability as Plugin `1.7.0`; Profile `0.1`, OKF `0.2` and Source Registry v1 remain unchanged.
- Keep generated Query behavior in canonical template version `1`. Delivery performs strict substitution only and never asks a model to generate instructions.
- Put closure, security, manifest and atomic-publication behavior in one deep module, `ad_wiki.delivery`; the root CLI and builder Skill remain thin.
- Generate a self-contained read-only Skill whose optional helper uses only the Python standard library. Agents without command execution navigate the same packaged files manually.
- Build exactly one directory artifact and never overwrite a changed target. Deployment, archives, Writeback and session capture remain out of scope.

## Scope deltas

- The user clarified that every generated `ad-${wiki-name}` must share stable Query logic and differ only in explicit Wiki identity/configuration/content. This makes canonical versioned templates a required implementation boundary.
- Existing local `.agents/skills`, `.claude`, stashes, other worktrees and source Wiki run state are excluded from implementation and delivery commits.

## Implementation units

### U1 — Canonical identity, templates and manifest contracts

- Requirements: R-SD1–R-SD3, R-SD7, R-SD13, R-SD14, R-SD16–R-SD18.
- Dependencies and accepted-design pointers: TechnicalDesign naming, template and Artifact Manifest sections.
- Affected modules and mutation: new delivery tests/module skeleton; `ad-wiki-ship` canonical templates; deterministic naming, strict placeholder rendering and payload identity helpers.
- Entry / exit conditions: enter from accepted design; exit when legal/illegal names, stable Query text, manifest schema and deterministic identity have red-to-green focused tests.
- Focused verification: naming table/property negatives, unknown placeholder failure, cross-output digest equality and generated frontmatter validation.
- Recovery checkpoint: additive files only; no existing behavior or version change yet.

### U2 — Exact evidence closure and deployability gates

- Requirements: R-SD5–R-SD12, R-SD15.
- Dependencies and accepted-design pointers: U1 contracts; existing Validator, Source Registry and Raw Guard.
- Affected modules and mutation: `scripts/ad_wiki/delivery.py`; Bundle/Raw allowlist, registry/source closure, path/symlink/special-file checks, local link/citation gates, streaming secret scan and source snapshot inventory.
- Entry / exit conditions: enter with deterministic contracts; exit when a valid fixture produces a complete candidate and invalid Bundle, changed/missing Raw, escaping path, ambiguous source, secret/private key and unsafe file fixtures fail closed without secret echo.
- Focused verification: exact Raw byte identity, external-source inventory, excluded-path inspection, source-before/after byte comparison and sensitive negative cases.
- Recovery checkpoint: candidate creation remains temporary and unpublished until U3.
- Complexity allowance: one cohesive delivery module is authorized by the cross-cutting immutable-artifact invariant; small private helpers remain local.

### U3 — Self-contained Query helper and atomic publication

- Requirements: R-SD4–R-SD6, R-SD9–R-SD10, R-SD14–R-SD18.
- Dependencies and accepted-design pointers: U1/U2; generated Skill and failure-flow sections.
- Affected modules and mutation: standalone `delivery_query.py`, generated wrapper, candidate validation, manifest finalization, identical/conflicting target handling and sibling atomic rename.
- Entry / exit conditions: enter with exact candidate closure; exit when compiled Query and bounded registered-Raw fallback work with helper, manual instructions remain sufficient without scripts, repeated builds are unchanged and injected failures leave no target/temp residue.
- Focused verification: helper integrity/bounds/path negatives, no-write tree digest, two-output reproducibility, source drift injection, conflict/no-overwrite and fault cleanup.
- Recovery checkpoint: source remains byte-identical and published artifact can be removed independently.

### U4 — Builder Skill, CLI and Plugin 1.7 packaging

- Requirements: R-SD1–R-SD4, R-SD16–R-SD18.
- Dependencies and accepted-design pointers: U1–U3 public Python result and command contract.
- Affected modules and mutation: `skills/ad-wiki-ship`, `scripts/build_wiki_skill.py`, CLI adapter/export, doctor/package manifests/templates/docs and version identities.
- Entry / exit conditions: enter with Python builder green; exit when both hosts discover the fourth builder Skill, JSON/exit behavior is stable, all Plugin surfaces report `1.7.0` and old commands remain compatible.
- Focused verification: CLI created/unchanged/error journeys, builder Skill validator, Codex/Claude Plugin validators, doctor, package assertions and release identity search.
- Recovery checkpoint: CLI/Skill/version changes are additive and independently reversible with the builder module.

### U5 — Real Wiki proof, final verification and delivery

- Requirements: all.
- Dependencies and accepted-design pointers: U1–U4 and TechnicalDesign risks/verification section.
- Affected modules and mutation: convergent fixes/tests/docs only; Git/PR publication after verification and review.
- Entry / exit conditions: enter with fixture suite green; exit at a merge-ready PR without merging.
- Focused verification: full unit suite, Ruff, compileall, frozen lock, diff check, four Skill validators, Plugin validators, doctor and real `sofa-wiki` build proving four registered Yuque sources, external code-source inventory, `.ad-wiki/runs` exclusion and representative compiled/Raw Query journeys.
- Recovery checkpoint: delivery commit(s) on the isolated feature branch; no force push unless a later rebase requires `--force-with-lease`.

## Verification contract

- Required engineering evidence: focused delivery tests plus all repository tests; Ruff; compileall; `uv lock --check`; `git diff --check`; Codex/Claude Plugin validators; four Skill validators; doctor.
- Required security evidence: secret/private-key/denied-name/path/symlink/source-drift/output-conflict fixtures; no matched secret text, source absolute path, excluded state or mutation in the artifact/report.
- Required compatibility evidence: existing init/query/maintainer/code-wiki/health/transaction tests remain green; existing Profile/OKF/Registry versions and commands do not migrate.
- Required product journey: build real `sofa-wiki` outside both source and product repositories, inspect manifest/counts/digests/exclusions, then answer one compiled question and one registered-Raw fallback question with and without helper execution.
- Required reproducibility evidence: identical source/options in different output parents have identical payload/manifest content identities; an identical target returns `unchanged`, a different target remains untouched and fails.
- Human experience: user review of installed-host triggering is not impersonated; repository validators and fresh-file-only Query journeys prove the engineering boundary.

## Risks and recovery

- Raw redistribution leaks credentials: strict registry closure, high-confidence scanning and no override.
- Canonical template drift: explicit template version, byte-stable tests and no model generation.
- Incomplete or misleading provenance: exact Raw digest checks, source-to-registry closure and external-source manifest inventory.
- Partial output or source mutation: sibling temp build, source recheck, atomic rename and fail-without-overwrite behavior.
- Large Wiki memory/cost: streaming copy/hash/scan with bounded file count/path length and no arbitrary total-byte cap.
- Rebase conflict: fetch/rebase latest `origin/main`, preserve current main behavior, compare final tree and use only `--force-with-lease` if the already-published branch later requires it.

## Definition of done

- Every R-SD requirement is implemented and backed by engineering evidence without adding deployment, Writeback or runtime Plugin dependency.
- Product Contract, accepted TechnicalDesign, implementation and generated template behavior agree; no open product or technical decision remains.
- Full verification passes on the final tree and independent code review has no blocking finding.
- Scoped commits are pushed and one PR is open, current with `main`, CI/reviews have no actionable failures, and the PR is honestly merge-ready without being merged.
