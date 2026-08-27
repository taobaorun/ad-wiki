# Implementation Plan: AD Wiki 分级评审写回与代码源重定位

Product Contract: `docs/product-specs/ad-wiki-reviewed-writeback-and-code-source-resolution.md`

Technical Design: `docs/designs/ad-wiki-reviewed-writeback-code-source-resolution.md`

Requirements: R-WB1–R-WB11, R-CS1–R-CS6

Commit policy / authority: `none`；用户通过 `ad-gallop` 授权当前仓库工作树修改与 `local-complete`，未授权 commit、push、PR 或发布。

## Implementation decisions

- 使用可选 `review_reasons` 区分受门禁的 Query 派生事务；不按 risk 自动改变所有 Maintainer 工作流。
- 复用现有 `REVIEW_REQUIRED` 状态、staged hash、baseline、Raw guard、锁和 rollback；新增通用 freeze，不恢复旧 owner/approval 模型。
- candidate digest 绑定 run/write/evidence/impact/baseline 内容；Runtime 不记录用户话术或身份。
- 新建 `code_sources` 深模块统一 Git identity、portable registry、private binding 和 resolver；`code_wiki` 保持兼容导出。
- portable registry 位于 `.ad-wiki/code-source-registry.json`；private binding 位于被 Git 与交付排除的 `.ad-wiki/cache/code-worktrees/`。
- 旧 run/仓库采用 tolerant read 和显式幂等 rebuild，不提升 Profile、不做破坏性 contraction。
- 自动候选仅由 Query 合同约束当前对话行为；用户自然语言触发现有 Maintainer，不新增 Skill。

## Scope deltas

无。版本发布、提交、远端发布、通用审批系统、跨 Wiki/主机 binding 同步和候选 inbox 均不在本计划内。

## Implementation units

### U1 — 冻结并精确 Apply 受评审 Writeback

- Requirements: R-WB2–R-WB8。
- Dependencies and accepted-design pointers: Technical Design 的 “Generic transaction API”“Review candidate v1”“State and recovery”。
- Affected modules and mutation: `scripts/ad_wiki/runtime.py`、`scripts/ad_wiki/cli.py`、`scripts/ad_wiki/__init__.py`、新增 `scripts/freeze_run.py`，以及 `tests/test_runtime.py`、`tests/test_cli.py`；扩展 prepare 的 evidence/impact 输入、实现 `freeze_run`、为 `apply_run` 增加 digest 门禁，保留 legacy run 兼容。
- Entry / exit conditions: entry 为当前 direct-Apply 测试基线可复现；exit 为 gated run 在 freeze 前不能 Apply、legacy reporter 不能覆盖 transaction run、schema-v2 lineage 在 gate payload 丢失/legacy state 篡改时 fail closed、multi-turn/risk labels 不能降级或矛盾、freeze 不改 live Wiki且必须绑定 impact/evidence、正确 digest 可 Apply、nested/top-level staged/write/evidence/impact/baseline 漂移失败，ungated low-risk 与 genuine legacy approved fixtures 不回归。
- Focused verification: `python3 -m unittest tests.test_runtime tests.test_cli -v`，覆盖 API 与 CLI common/edge/failure examples。
- Recovery checkpoint: 该单元仅触及事务/CLI seam；失败时撤销这些路径的本轮 hunks，ProductContract/TechnicalDesign/Plan 和其他单元保持可用。
- Complexity allowance: 允许一个新的 freeze public command 和 review-candidate schema；R-WB4/R-WB6 要求 Runtime 机械绑定已评审内容，Skill-only 方案不足。

### U2 — 可移植代码源身份与本机 worktree resolver

- Requirements: R-CS1–R-CS5。
- Dependencies and accepted-design pointers: Technical Design 的 `code_sources` module、portable/private schemas、Code worktree API 与 Security 部分。
- Affected modules and mutation: 新增 `scripts/ad_wiki/code_sources.py`、`scripts/ad_wiki/locking.py`、`scripts/bind_code_worktree.py`、`scripts/resolve_code_worktree.py`；调整 `scripts/ad_wiki/runtime.py`、`scripts/ad_wiki/code_wiki.py`、`scripts/ad_wiki/code_index/cache.py`、`scripts/ad_wiki/cli.py`、`scripts/ad_wiki/__init__.py`；新增 focused registry/resolver/concurrency tests。
- Entry / exit conditions: entry 为现有 `inspect_code_repository`/`repository_key` 行为有测试覆盖；exit 为 portable identity 不含本机路径/凭据，所有 mutator/resolver 在写状态前验证 Wiki/Profile，binding 的完整 read/merge/write 与 registry rebuild 共享 repository writer exclusion，binding 原子私有写入且拒绝任一 cache path symlink/损坏 gitignore，Python API/CLI 都使用 `repository_key`，resolver 对 exact/missing/ambiguous/wrong-remote/wrong-root/missing-revision/dirty-required/symlink 场景 fail-safe，revision-qualified 结果强制 `git-object` 读取模式，且不扫描或 clone。
- Focused verification: 新增 `tests/test_code_sources.py`，并运行 `python3 -m unittest tests.test_code_sources tests.test_code_wiki tests.test_code_index -v`。
- Recovery checkpoint: 新模块未接入 Code Wiki Apply 前可独立撤销；接入后以现有 Code Wiki focused tests 作为兼容恢复边界。
- Complexity allowance: 允许一个共享 `code_sources` 模块和两个 CLI；当前 identity/resolution 跨 Code Wiki、Code Index、Query/Maintainer 且安全策略易漂移，集中后接口更小。

### U3 — Code Wiki validated registry、旧 run rebuild 与交付边界

- Requirements: R-CS1–R-CS6。
- Dependencies and accepted-design pointers: U2；Technical Design 的 Compatibility and migration。
- Affected modules and mutation: `scripts/ad_wiki/core.py`、`scripts/ad_wiki/runtime.py`、`scripts/ad_wiki/code_wiki.py`、`scripts/ad_wiki/doctor.py`、新增 `scripts/rebuild_code_source_registry.py`，以及 `tests/test_core.py`、`tests/test_code_wiki.py`、`tests/test_delivery.py`、`tests/test_packaging.py`；Init 创建空 registry，Code Wiki Apply 在现有事务/rollback 中合并 validated snapshot，rebuild 从 validated historical runs 幂等恢复。
- Entry / exit conditions: entry 为 U2 schema/atomic helpers 完成；exit 为新仓初始化可用、旧仓缺 registry 仍可读、portable snapshot 只在 durable VALIDATED 后发布且中断可由 completed-Apply 或 Review 幂等修复、后续 rejected Review 不丢失、失败 Apply 能回滚 registry、incremental 与 rebuild 字节一致、所有 lexical registry/run/summary symlink 与 invalid-JSON/JSON-valid malformed/unreadable historical run 在替换前 fail closed、version 仅接受 exact integer 1，unknown/wrong-typed fields/incomplete legacy provenance/unsafe names 均以 structured error fail closed、binding/cache 不进入 Skill delivery。
- Focused verification: `python3 -m unittest tests.test_core tests.test_code_wiki tests.test_delivery tests.test_packaging -v`，并运行新 CLI 的临时仓 smoke journey。
- Recovery checkpoint: registry 更新纳入 Apply snapshot；任何 post-apply 失败必须同时恢复 Bundle 与 registry。实现失败可保留 U2 私有 resolver，而不声明 portable validated snapshot 已交付。
- Complexity allowance: 允许一个 rebuild public command作为旧持久数据的 expand-only compatibility seam；不得添加 Profile migration 或自动 workspace discovery。

### U4 — Query 候选生命周期与 Maintainer 两阶段交互

- Requirements: R-WB1–R-WB11。
- Dependencies and accepted-design pointers: U1；Technical Design 的 Skills and portable Query contract。
- Affected modules and mutation: `skills/ad-wiki-query/SKILL.md`、`skills/ad-wiki-query/references/query-contract.md`、`skills/ad-wiki-maintainer/SKILL.md`、`skills/ad-wiki-maintainer/references/workflows.md`、`skills/ad-wiki-maintainer/references/risk-policy.md`、`skills/ad-code-wiki/SKILL.md`、`scripts/ad_wiki/core.py` 的 static `AGENTS.md`、`examples/minimal-wiki/AGENTS.md`，以及 packaging/static-contract tests。
- Entry / exit conditions: entry 为 U1 CLI 行为稳定；exit 为 Query 自动维护一个 ephemeral 当前候选、只在收敛条件提示一次、自然语言 staging handoff 明确、Maintainer 对 gated flow freeze 后停止、后续 Apply 使用 digest；Code Wiki Prepare 记录明确 worktree binding，Query 对 code source 先 exact resolve、缺失时询问且不扫描；普通 compiled hit、关键证据未决和 standalone delivered Skill 不获得写能力。
- Focused verification: `python3 -m unittest tests.test_packaging tests.test_core tests.test_delivery -v`，加静态契约断言和代表性 multi-turn/ordinary-hit journey fixtures（若仓库没有模型执行 harness，则静态断言为 required，人工/宿主 journey 记为 experiential evidence）。
- Recovery checkpoint: Skill/AGENTS 文本变更与 Runtime 分离；若宿主行为不收敛，保留 U1 安全门禁并回退主动提示文案，不回退 ProductContract。
- Complexity allowance: none；不创建新 Skill、持久 candidate store 或路由框架。

### U5 — 整体兼容、质量与 as-built 文档同步

- Requirements: R-WB1–R-WB11、R-CS1–R-CS6。
- Dependencies and accepted-design pointers: U1–U4。
- Affected modules and mutation: 只修复由前述单元直接造成的集成问题；按实际实现同步 TechnicalDesign，不扩写产品范围。
- Entry / exit conditions: entry 为所有 focused suites 通过；exit 为 full suite、compileall、lint/format、Plugin doctor、临时仓 CLI journey、delivery privacy 与 `git diff --check` 全部通过，且 TechnicalDesign 与实现一致。
- Focused verification: 见 Verification contract。
- Recovery checkpoint: 对失败检查回到最小 owning unit；任何修复后仅重跑受影响 focused checks，再重跑最终 full gate。
- Complexity allowance: none；不得借最终集成做邻近重构或版本发布。

## Verification contract

- Baseline, required: mutation 前记录 `git status --short`、`python3 -m unittest discover -s tests -v`、`python3 -m compileall -q scripts tests` 和 `git diff --check`；既有失败必须与本任务分离。
- Focused, required: 每个 Unit 所列 unittest module；所有状态/registry/resolver 负向分支必须有自动化证据。
- Cross-unit, required: 临时 Wiki 执行 Init → gated prepare → stage → freeze → wrong digest rejection → correct Apply → Validate，以及 bind → resolve → rebuild registry journeys。
- Full, required: `python3 -m unittest discover -s tests -v`、`python3 -m compileall -q scripts tests`、`git diff --check`、`python3 scripts/doctor_plugin.py --plugin-root . --json`。
- Preferred: `ruff check scripts tests`；若 Ruff 在环境中不可用，fallback 为 compileall + unittest + diff-check，fidelity loss 是缺少静态 lint，authority 为本 Plan 的本地完成边界。
- Packaging/release, required where repository-native: Plugin doctor 与现有 packaging/delivery tests；没有独立 release build 命令时不得虚构。
- Security specialist evidence, required: credentialed/local remotes、symlink worktree、path leak、ambiguous candidate、private cache delivery exclusion的负向测试。
- Migration specialist evidence, required: old run without new fields、legacy approved hashes、missing registry、idempotent rebuild、Apply rollback parity。
- Experiential acceptance: owner 为用户；确认多轮候选提示不吵闹、`准备写回` 与后续 `apply` 语义清楚、staged 链接可读。工程验证可标为 verified，但在用户未亲自体验前该项为 `pending-human`，不阻塞本轮 `local-complete`。

## Risks and recovery

- Runtime gate 与 Skill 文案可能不一致：Runtime tests 与 static contract assertions 双向约束。
- Registry 成为第二真相：只接受 validated Code Wiki run 写入，并以 deterministic rebuild parity 检测漂移。
- 本机路径泄漏：private cache、safe remote normalization、delivery tests 和仓库 diff 扫描共同防护。
- Legacy approval 语义复活：只兼容读取旧字段，新 flow 不写 actor/approvals；测试断言新 run 不含旧字段。
- 自动候选噪声无法完全由 deterministic tests 证明：保留一个 current candidate、收敛触发和 pending-human 验收；不增加持久按钮/命令。
- 当前工作树含用户未跟踪 `.agents/skills/`、`.claude/`：实现和验证不得修改、删除或纳入任何交付判断。

## Definition of done

- 全部 17 个需求都有实现路径和自动/体验证据。
- gated Query-derived Writeback 在用户第二次确认前不能修改 live Wiki，且确认绑定精确候选。
- single-turn low-risk 与 legacy run 行为保持兼容。
- 新会话可通过 portable identity + private binding 精确恢复代码 worktree；失败时询问，不扫描。
- portable registry 与旧 run rebuild 一致，Apply 失败时可回滚。
- Query 自动候选不持久化、不自动 staging、不新增 Skill。
- focused/full/doctor/compile/diff gates 通过，安全与迁移负向测试覆盖。
- ProductContract、TechnicalDesign 与实现一致。
- 工作树达到 `local-complete`；不 commit、不 push、不开 PR、不发布。
