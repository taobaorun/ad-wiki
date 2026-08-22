# Implementation Plan: AD Code Wiki 结构智能 v1.5

Product Contract: in-run `code-wiki-structural-intelligence-2026-08-22`

Technical Design: `docs/designs/ad-code-wiki-structural-intelligence-v1.5.md`

Requirements: R-CI1–R-CI15

Commit policy / authority: `none`；用户于 2026-08-22 授权本地实施，未授权 commit、push、PR 或发布。

## Implementation decisions

- 保持 `1.4.0` model-only Code Wiki 默认行为；`1.5.0` 通过显式 `--structural-index` 启用结构模式，缺依赖时 fail closed。
- 新增独立 `code-index/pyproject.toml + uv.lock`，只包含 pinned tree-sitter/Java grammar；基础 Plugin Runtime 不 import 这些包。
- 自有 `ad_wiki.code_index` 使用 plain dict/list JSON graph，不依赖 Graphify、NetworkX、RapidFuzz、Leiden 或 LLM SDK。
- 一期 providers 为 Java AST、Maven/XML、Properties；stable ID、Fragment/Graph schema、evidence enums、summary/vocab 由共享核心固定。
- Cache/graph/manifest/bindings 位于 `.ad-wiki/cache/code-index/<repo-key>/`，目录自带忽略规则；全部是可删除重建视图。
- Structural query 和 impact 通过三个薄 CLI；Code Wiki 只消费 bounded subgraph，并用 code_refs v2 绑定最终页面。
- 目标版本 `1.5.0`；Profile `0.1`、OKF `0.2` 不迁移。

## Scope deltas

- 用户明确授权直接依赖 `tree-sitter`/`tree-sitter-java`，但要求永不依赖 Graphify。
- Java/SOFA 是首个发布语言；多语言 extractor、Graph UI、community/fuzzy dedup、watcher/query log 均不在本计划。
- Structural mode 是 additive opt-in；不改变现有 Query/Maintainer/Init 和 model-only Code Wiki。

## Implementation units

### U1 — Locked environment、schema、ID 与安全边界

- Requirements: R-CI1、R-CI4–R-CI7、R-CI14
- Dependencies and accepted-design pointers: Design §4、§7–8、§15
- Affected modules and mutation: `code-index/pyproject.toml`、`uv.lock`；`scripts/ad_wiki/code_index/{model,ids,security}.py`；small unit/property tests。
- Entry / exit conditions: 相同输入生成稳定 JSON；case-sensitive Java IDs、location/evidence/schema validation、file/binary/path/size/control-char limits 均 proof-first；基础 tests 在无 structural env 下仍运行。
- Focused verification: uv frozen import；ID repo-move/case/signature tests；Fragment/Graph malformed/dangling/duplicate/oversize negative tests；security path/binary/control-char tests。
- Recovery checkpoint: 新 package 未被 Code Wiki 调用，可整体移除而不影响 `1.4.0`。
- Complexity allowance: owned schema/ID/security modules 由 cross-run bindings 和 untrusted code requirement 授权；不创建 generic graph framework。

### U2 — Java/SOFA extractors、resolution 与 deterministic graph

- Requirements: R-CI2–R-CI8
- Dependencies and accepted-design pointers: U1 schema；Design §6–9、§11
- Affected modules and mutation: extractor protocol/registry；Java tree-sitter provider；Maven/XML/Properties providers；global resolver、graph assembler、summaries/vocab；fixtures/tests。
- Entry / exit conditions: Java declarations/imports/inheritance/calls/annotations/tests、Maven dependency/plugin/property 和 properties placeholder facts 被提取；直接/唯一解析/多候选关系分别 EXTRACTED/INFERRED/AMBIGUOUS；worker order 不改变 graph bytes。
- Focused verification: Java fixture matrix；XML external-entity rejection；properties secret redaction；unresolved nodes；cross-file unique/ambiguous calls；worker=1/4 determinism；300-char summaries和真实 vocab。
- Recovery checkpoint: U1 schema stable；providers/graph 可按语言独立禁用。
- Complexity allowance: Extractor protocol 由三个真实 providers 授权；ProcessPool deterministic merge 由全 repo 性能和 Graphify research evidence授权。

### U3 — Content cache、atomic manifest、query 与 impact

- Requirements: R-CI8–R-CI12、R-CI14–R-CI15
- Dependencies and accepted-design pointers: U2 stable fragments/graph；Design §10–12、§14–16
- Affected modules and mutation: `cache.py`、`query.py`；build/query/impact CLIs；`.ad-wiki/cache` layout；incremental/query tests。
- Entry / exit conditions: no-op cache hit、add/change/delete/rename、version miss、corrupt cache、atomic crash recovery；search/explain/path/BFS/DFS/affected budgets和ambiguity；query无写回/日志。
- Focused verification: manifest-last publish injection failure；fragment key changes；prune+global resolution；zero-match/ambiguous/path-none；affected reverse location；hard caps/truncation。
- Recovery checkpoint: cache 可删除全量重建；Bundle 和 `1.4.0` run state不变。
- Complexity allowance: atomic cache/manifest 和 bounded query 由 R-CI9–R-CI12 授权；不加 daemon/UI/NetworkX。

### U4 — Code Wiki structural integration、bindings 与 1.5 contracts

- Requirements: R-CI1–R-CI15
- Dependencies and accepted-design pointers: U1–U3 public seams；Design §13、§17、§19
- Affected modules and mutation: `prepare/checkpoint/finalize_code_wiki` structural flag/schema；code_refs v2 validation；bindings publish CLI；`ad-code-wiki` Skill/reference；Product Contract/team docs；Manifest/Runtime/templates `1.5.0`；integration/packaging tests。
- Entry / exit conditions: 无 flag 完全保持 v1；有 flag 绑定 graph/manifest digest、vocab tokens、v2 refs；Apply success 后发布 bindings；增量 affected Concept 或 >60%/ambiguity/full fallback；三个 Skill/Plugin validators通过。
- Focused verification: model-only regression；structural dependency fail closed；wrong symbol/relation/revision rejection；bindings after Apply only；first full run + second incremental fixture；SOFA-style Java/POM/properties journey。
- Recovery checkpoint: structural integration hunks 可关闭/回退而保留 U1–U3 standalone commands；版本最后切换。
- Complexity allowance: explicit mode兼容层由 minor-version non-breaking requirement授权；不添加自动 mode detection。

## Verification contract

- Required baseline: 现有 84 tests、Ruff、compileall、Plugin/三 Skill validators。
- Required source proof: tree-sitter Python/Java versions与官方 API/compatibility source；`uv lock --check`/`uv run --frozen`。
- Required focused: each unit tests above, RED before GREEN for new behavior。
- Required full: `python3 -m unittest discover -s tests -v`、Ruff、compileall、`git diff --check`、Plugin validator、三 Skill validators、Claude strict validator。
- Required determinism/isolation: graph bytes across checkout roots/workers equal；code repo bytes/status不变；cache deletion rebuild equal；另一个 Wiki不变；model-only path无 tree-sitter import。
- Required behavioral: first structural full fixture + second incremental revision；document query/base Concept、source query/Companion、affected Concept refresh、partial/ambiguity诚实。
- Preferred experiential: 完整 SOFA Wiki + latest SOFA code repo 对比 1.4 model-only / 1.5 structural 的匹配正确率、raw files read、needs-review/no-code-match、wall time/RSS。
- Fallback experiential: 若真实 SOFA repo 未提供，Java/POM/properties fixture只证明工程行为，不能替代发布验收。
- Experiential owner: 用户；缺失真实 SOFA evidence阻止发布结论，不阻止本地实现完成。

## Risks and recovery

- tree-sitter API/grammar drift：uv lock、official API source、grammar version cache key和fixture。
- Java resolution false positive：直接/唯一/多候选 evidence分层，无 fuzzy winner。
- Incremental stale graph：changed fragments后全局重解引用、schema validation、manifest-last atomic publish。
- Cache/graph resource pressure：pre-read limits、bounded graph/query/snippets、measure SOFA baseline。
- Base Plugin dependency regression：isolated env、explicit flag、无 flag tests禁止 structural import。
- Current worktree already contains uncommitted 1.4 implementation：所有 v1.5 hunks必须 trace到本 Plan，不覆盖/重写 1.4 unrelated changes。

Recovery：cache是可重建视图；删除 cache触发 full build。Structural Apply仍复用现有 Wiki rollback；bindings只在 Apply success后发布。无 commit policy，当前隔离 worktree是恢复边界。

## Definition of done

- AD Wiki 无 Graphify dependency/reference in runtime。
- Java/POM/Properties structural graph deterministic、validated、evidence-tagged、stable-ID。
- search/explain/path/BFS/DFS/affected bounded且诚实处理歧义。
- content cache、atomic manifest、incremental prune/global resolution和bindings可恢复。
- `--structural-index` additive；model-only v1完全回归。
- Code refs v2绑定 graph evidence，Companion仍从原始源码生成。
- 全量工程验证通过；真实 SOFA验收若缺失明确留作发布 residual。
