# Implementation Plan: AD Wiki Primary-Source Context and Health v1.6

Product Contract: `docs/product-specs/ad-wiki-primary-source-context.md`

Technical Design: `docs/designs/ad-wiki-primary-source-health-v1.6.md`

Requirements: R-PSC1–R-PSC12, R-HM1–R-HM15

Commit policy / authority: `delivery-only`; explicit `ad-gallop` invocation authorizes scoped commits, push, one PR and convergence to merge-ready, but not merge.

## Implementation decisions

- Release the combined capability as Plugin `1.6.0`; preserve Profile `0.1`, OKF `0.2`, Source Registry v1 and existing public commands.
- Use one new deep `ad_wiki.health` module and a thin root CLI. Do not distribute metric logic across Validator, Query and Code Wiki owners.
- Deterministic facts and optional Assessment v1 are separate inputs. Missing semantic evidence returns `unavailable`; it is never guessed from repository shape.
- Health inspection is read-only and network-free. Automatic upstream Primary Source descent remains host-Agent behavior in Query Skill/static contract.

## Scope deltas

- The user-provided DeepWiki/Karpathy practices and explicit health-metric request authorize ToC/Glossary assets, Assessment/Report v1 and metric computation beyond the earlier `1.5.1` Query-only patch.
- Existing unrelated primary-worktree changes, ad-harness Skill symlink repair and legacy exec-plan layout findings are excluded.

## Implementation units

### U1 — Primary Source Query and example provenance
- Requirements: R-PSC1–R-PSC8, R-PSC12, R-HM11.
- Dependencies and accepted-design pointers: TechnicalDesign Query/security sections.
- Affected modules and mutation: Query Skill/reference, static AGENTS generator/example, bounded Raw retrieval, minimal example locator/partial coverage/source identity, version-neutral tests.
- Entry / exit conditions: enter with current uncommitted Query patch reconciled to Product Contract; exit when compiled hit remains Raw-free, exact local/upstream descent is automatic/no-question in behavior contract and example provenance is internally consistent.
- Focused verification: Query packaging/static tests, Raw fallback fixtures, real SOFA health-check replay, example validation/hash checks.
- Recovery checkpoint: file-level diff; no commit until delivery.

### U2 — Health Report and Assessment contracts
- Requirements: R-PSC11, R-HM1–R-HM5, R-HM7–R-HM15.
- Dependencies and accepted-design pointers: TechnicalDesign Public interfaces and security limits.
- Affected modules and mutation: new `scripts/ad_wiki/health.py`, package export, assessment/report schema validation, unit tests.
- Entry / exit conditions: enter with stable validator primitives; exit when valid/invalid/unavailable vectors serialize deterministically, reject unsafe/oversized inputs and cannot contain an overall score.
- Focused verification: small schema/property/negative tests, deterministic serialization, no-write byte comparison.
- Recovery checkpoint: new module/tests removable without altering existing APIs.
- Complexity allowance: one public module/API is authorized by the new cross-command Health Report contract; private metric helpers stay local.

### U3 — Deterministic Wiki correctness and maintenance metrics
- Requirements: R-HM2, R-HM7, R-HM8.
- Dependencies and accepted-design pointers: U2 report builder; existing validator/Raw registry.
- Affected modules and mutation: health collectors for source integrity, citations, managed links, stale/orphan/index drift, source-to-concept yield, findings/evidence.
- Entry / exit conditions: enter with schema green; exit when every deterministic metric has traceable numerator/denominator and hard-gate failures produce `unhealthy`.
- Focused verification: healthy/broken/tampered/stale/orphan/partial-source fixtures and exact overall-state assertions.
- Recovery checkpoint: U2 schema remains usable with metrics unavailable if collectors are reverted.

### U4 — Optional code and semantic/experiential metrics
- Requirements: R-PSC9–R-PSC11, R-HM3–R-HM14.
- Dependencies and accepted-design pointers: U2/U3; existing Code Wiki graph/bindings.
- Affected modules and mutation: assessment-backed calculations, clean Git/graph/binding inspection, active-code coverage, code gates, unknown-unknown signals, representative questions/path compression/scale/usefulness tests.
- Entry / exit conditions: enter with deterministic report stable; exit when matching evidence calculates metrics, mismatched revisions fail or become unavailable as designed, missing optional inputs remain honest.
- Focused verification: code repo/graph fixtures, assessment revision/limit/unknown-field negatives, privacy assertions, no code-repo mutation.
- Recovery checkpoint: optional collectors are isolated behind absent-input unavailable results.
- Complexity allowance: Assessment v1 is authorized because semantic/experiential denominators cannot be derived truthfully by deterministic code alone.

### U5 — CLI, Skills, ToC/Glossary assets and release packaging
- Requirements: R-PSC2, R-PSC8–R-PSC12, R-HM1–R-HM15.
- Dependencies and accepted-design pointers: U1–U4.
- Affected modules and mutation: `health_main`, `inspect_wiki_health.py`, doctor/package exports, Maintainer/Query/Code Wiki instructions and references, ToC/Glossary/assessment assets, manifests/templates/docs to `1.6.0`, packaging/CLI tests.
- Entry / exit conditions: enter with Python API complete; exit when both hosts package/discover the command/assets, Maintainer can produce semantic evidence without logging ordinary Query and CLI exit behavior matches design.
- Focused verification: CLI journeys with/without assessment/code repo/`--require-healthy`, three Skill validators, Codex/Claude Plugin validators, doctor.
- Recovery checkpoint: root CLI and assets are additive and independently removable.

### U6 — Integrated proof and delivery
- Requirements: all.
- Dependencies and accepted-design pointers: U1–U5.
- Affected modules and mutation: tests/docs only for convergent failures; Git/PR publication after verify/review.
- Entry / exit conditions: enter with implementation complete; exit at merge-ready PR without merging.
- Focused verification: full unit suite, frozen lock, Ruff, compileall, diff check, Plugin/Skill validators, minimal example doctor, real SOFA Raw replay, read-only health journeys and code-repo byte/status comparison.
- Recovery checkpoint: delivery commit(s) on isolated feature branch; no force push unless later rebase requires `--force-with-lease`.

## Verification contract

- Required engineering evidence: all repository tests; focused Health/Query/Code Wiki negatives; Ruff; compileall; `uv lock --check`; `git diff --check`; Codex/Claude Plugin validators; three Skill validators; doctor.
- Required security evidence: repo-contained assessment, symlink/size/unknown-field rejection; no source contents/question text/absolute paths in report; code repo and Wiki unchanged by inspection.
- Required compatibility evidence: existing Query, Init, Validate, transaction, model-only Code Wiki and structural Code Wiki tests unchanged except intentional version/static-contract assertions.
- Preferred experiential evidence: logged-in fresh Claude/Codex Skill-trigger journeys. Fallback when host authentication is unavailable: Plugin discovery/init evidence plus exact session residual; fidelity loss is automatic-trigger behavior only.
- Required product journey: SOFA health-check Raw fallback returns the exact health document; health inspection without semantic evidence is `incomplete`, with fixture assessment is deterministic and can become healthy/unhealthy based on gates.
- Human experience: user review of the PR/metrics is not impersonated; no separate pre-merge acceptance was required by the Product Contract.

## Risks and recovery

- Metric overclaim: unavailable-by-default semantic metrics, strict report validation and object evidence.
- Scope explosion: no central service, UI, automatic network, general telemetry or new Profile schema.
- Private repository exposure: local-only calculation, repo-relative output, no persisted questions or source bodies.
- Version/provenance drift: manifest/template/example/source registry tests and one release identity.
- Rebase conflict: fetch/rebase latest `origin/main`, preserve current main behavior, compare final tree and use only `--force-with-lease` if the already-published branch later requires it.

## Definition of done

- Every R-PSC/R-HM requirement is implemented, explicitly unavailable by contract, or proven by Skill/static behavior without hidden assumptions.
- TechnicalDesign and Product Contract match the shipped interface and no open decision remains.
- Full verification passes on the final tree; independent code review has no blocking finding.
- Scoped commits are pushed and one PR is open, current with `main`, CI/reviews have no actionable failures, and the PR is honestly merge-ready without being merged.
