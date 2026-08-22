# Product Contract: AD-Wiki 仓库本地 Wiki 构建能力

Authority: 用户于 2026-08-16 确认仓库本地产品定位；于 2026-08-19 删除本地前置审批；于 2026-08-20 确认千页以内由模型直接导航 Wiki，完整删除 Discovery/Hydration/Context Builder，不保留兼容入口；于 2026-08-21 确认 Wiki 必须通过静态入口服务不具备脚本执行能力的 Agent；于 2026-08-22 确认基础 Wiki 完成后可独立运行全库自动 Code Wiki 编译，并确认 Java/SOFA-first 自建 tree-sitter 结构索引且永不依赖 Graphify

Product Context: 本文同时记录当前版本的持久产品边界。

## Actor and observable outcome

团队成员通过统一分发的 AD-Wiki Plugin，在自己有权访问的单个 Git 仓库中，把不可变 Raw Sources 持续编译为可读、可追溯、可审查的 OKF Wiki。

用户安装 Plugin 后，可以在不依赖 AD-Wiki 中央服务的情况下完成初始化、来源登记、Ingest、只读 Query、Writeback、Lint、Migrate，以及 baseline-bound、可校验、失败可回滚的知识写入事务。模型直接使用 Wiki 的索引、链接和 Markdown 内容，不在阅读前经过 AD-Wiki 自建的相关性过滤层。

## Requirements

- R1 — AD-Wiki 以可复用 Plugin、Skill、确定性维护脚本和仓库内静态 Agent 入口分发能力，不集中保存团队知识；acceptance: Plugin 包不包含具体团队知识或凭据，初始化仓库只保存通用查询契约和自身领域知识；owner/method: engineering，发行物检查；provenance: 用户对“AD-Wiki 只提供能力”的确认及 2026-08-21 的无脚本 Agent 要求。
- R2 — 每次操作显式绑定一个仓库根，不能扫描、检索或修改其他知识库；acceptance: 双仓库隔离测试中操作 A 后 B 字节不变；owner/method: engineering，自动化测试；provenance: 仓库本地边界。
- R3 — `raw/` 是不可变事实输入，`wiki/` 是 OKF Bundle，`.ad-wiki/` 保存 Bundle 外的本地运行状态；acceptance: Raw Guard、Bundle 校验和路径边界测试通过；owner/method: engineering，自动化测试；provenance: LLM-Wiki 与 OKF。
- R4 — 核心闭环不依赖远程 AD-Wiki 服务，编译知识 Query 也不依赖脚本执行；acceptance: 断网时本地 Init、Ingest、Query、Writeback、Lint 和 Migrate 仍可执行，只有文件读取能力的 Agent 可完成 compiled Query；owner/method: engineering，本地端到端与前向测试；provenance: 当前产品定位及 2026-08-21 的无脚本 Agent 要求。
- R5 — 当前版本不提供 Search MCP、BM25、向量检索、重排、中央索引或跨仓库检索；acceptance: Manifest 不声明相关能力，代码不包含未启用搜索配置或索引；owner/method: engineering，发行物检查；provenance: 用户于 2026-08-20 明确延期到真实千页级瓶颈后再评估。
- R6 — 当前版本不提供管理 App、组织身份、中央 ACL 或服务端审批台；acceptance: Plugin 不声明 App，权限和 Git Review 由现有团队系统负责；owner/method: engineering，发行物检查；provenance: 用户明确排除。
- R7 — 当前版本不提供服务端批量导入、Connector 调度、中央队列或跨仓库 Batch；acceptance: 无 Worker、Connector 凭据或中央 Batch 状态；owner/method: engineering，代码检查；provenance: 用户明确排除。
- R8 — 当前版本不提供 Attested Runtime；acceptance: 可读取 `Attested Computation`，但无 Executor、Attester 或 Receipt Store；owner/method: engineering，Profile 测试；provenance: DR-001。
- R9 — 未来中央平台设计不能为当前实现扩张授权；acceptance: 当前交付不依赖未来平台；owner/method: product/design owner，文档审查；provenance: 当前本地范围。
- R10 — 同一发行仓库能被 Codex 和 Claude Code 的原生 Plugin/Marketplace 发现；acceptance: 仓库根为唯一 Plugin 根，两端 Manifest/Marketplace 指向 `./`；owner/method: engineering，打包与安装验证；provenance: 双端兼容要求。
- R11 — 双端兼容不得复制两套 Maintainer、Query 或 Runtime；acceptance: 每个 Skill 只有一个 canonical 实现，初始化仓库以 `AGENTS.md` 保存唯一静态 Query 契约，`CLAUDE.md` 只作薄导入适配；owner/method: engineering，发行物与初始化检查；provenance: 统一分发要求及 2026-08-21 的静态入口决定。
- R12 — 两个宿主遵守相同仓库边界、Raw 不可变、引用和直接 Apply 事务规则；acceptance: 双宿主前向测试覆盖 Init、只读 Query 和一次 `prepare → apply` 写入；owner/method: engineering，前向测试；provenance: 双端兼容与直接 Apply 决策。
- R13 — 两个 Manifest 使用相同 Plugin 名和正式 SemVer；acceptance: 名称均为 `ad-wiki`、版本完全一致且无正式 cachebuster；owner/method: engineering，打包测试；provenance: 可升级性要求。
- R14 — 仓库根直接作为 Plugin 根，Skill 位于根级 `skills/`；acceptance: 无 `plugins/ad-wiki` 包装层；owner/method: engineering，目录测试；provenance: 已确认发行结构。
- R15 — 仓库本地写入不要求或生成前置审批；`apply_run.py` 直接消费完整 staged write set，并在锁内执行 baseline、Raw、路径、校验和回滚保护；acceptance: low/medium/high 新事务均可从 `PLANNED` Apply，旧批准事务仍校验已有 staged hash，`approve_run.py` 兼容 shim 不记录 actor 或改变状态；owner/method: engineering，状态机与负向测试；provenance: 用户于 2026-08-19 删除审批。
- R16 — Init 持久化内容语言，默认 `zh-CN`，允许 `en`；acceptance: 配置、Index、Log 和 Agent 生成内容遵循语言，Raw 与代码不翻译；owner/method: engineering，端到端测试；provenance: 用户确认。
- R17 — 面向用户的 Plugin Query 由独立只读 `ad-wiki-query` Skill 提供，静态 `AGENTS.md` 为未安装 Skill 的 Agent 提供等价的 compiled Query 基线；acceptance: Query Skill 不呈现写命令，Maintainer 不公开普通问答，无 Skill Agent 仍遵循索引优先、引用和知识缺口规则；owner/method: engineering，Skill/static contract 与前向测试；provenance: 用户确认职责边界及 2026-08-21 的可移植要求。
- R18 — 千页以内的 Query 和 Maintainer 影响分析由模型直接渐进导航 Wiki；acceptance: Agent 先读配置和索引，再以任意可用文件读取或仓库搜索能力定位 Bundle Markdown、读取模型判断相关的完整页面，并可迭代关键词；Shell、脚本与 `rg` 只是可选能力，不存在固定 Top-K、score threshold 或 pre-model 字符预算；owner/method: engineering，Skill/static contract 与真实问题前向测试；provenance: 用户于 2026-08-20 明确“完全信任模型检索，不要提前过滤”，并于 2026-08-21 排除 Query 脚本依赖。
- R19 — `search_wiki.py`、`build_query_context.py`、builtin scorer、Discovery Catalog、Hydration/Context Envelope 及其公开 API 必须完整删除且不保留兼容入口；acceptance: 活跃代码、脚本、Skill 和测试不包含这些入口；owner/method: engineering，静态和打包测试；provenance: 用户于 2026-08-20 明确不需要兼容。
- R20 — Query 保持只读并信任已经编译的 Wiki；acceptance: 正常命中只读取 Bundle，不运行事务、全量健康检查或 Raw Guard，查询前后仓库字节不变；owner/method: engineering，Skill contract 与字节对比；provenance: LLM-Wiki“编译一次、持续复用”。
- R21 — Wiki 缺少一个窄事实、但已读 Concept 明确声明登记来源时，具备命令执行能力的 Agent 可执行一次有界 Raw fallback；acceptance: fallback 由 Concept ID 限定来源、校验所读 Raw 哈希、不扫描全部 Raw、不写回，并在回答中区分 compiled knowledge 与 Raw；无命令执行能力的 Agent 跳过 fallback 并报告知识缺口；owner/method: engineering，CLI、静态契约和边界测试；provenance: 用户接受受控 cache miss 及 2026-08-21 的无脚本约束。
- R22 — 超过约 1000 页只是重新评估 BM25 的触发条件，不是当前配置或自动路由；acceptance: 新仓库不写 search provider/threshold，文档不承诺自动切换；owner/method: product/engineering，配置和文档检查；provenance: 用户于 2026-08-20 明确延期。
- R23 — Query 默认回答简洁、可移植，只在影响结论时披露证据边界；acceptance: 使用仓库相对 Concept 路径和 source ID，不输出绝对路径、搜索命令或内部遥测；owner/method: engineering，Skill contract 与前向测试；provenance: 用户反馈与跨宿主要求。
- R24 — Maintainer 把长 FAQ、教程和多主题来源编译成可独立回答的原子 Concept；acceptance: Source Summary 只承担 provenance 目录作用，`coverage: full` 仅在读完整来源后使用，partial 必须披露范围且导入不得报告完成；owner/method: engineering，模板、Lint 和行为测试；provenance: sofa-wiki 评测。
- R25 — Wiki 内部关系使用标准 Markdown Bundle 链接；acceptance: 模板和 Skill 禁止 `[[wikilinks]]`，Validator 报告不支持语法与不存在目标；owner/method: engineering，验证测试；provenance: sofa-wiki 中 284 个不可识别链接的评测证据。
- R26 — Init 必须在目标仓库内创建 canonical `AGENTS.md` 静态 Query 契约和仅导入它的 `CLAUDE.md` 薄适配，但不得覆盖非同内容既有文件；除 Init 外，Maintainer 和 Query 不得写 host memory、这些入口文件、全局配置或目标仓库外文件；acceptance: Init 幂等、冲突时预检失败，Query 前后入口与仓库字节不变；owner/method: engineering，初始化、冲突与行为测试；provenance: 被评测会话的外部 memory 写入风险及用户 2026-08-21 明确采用静态入口方案。
- R27 — `domain` 描述整个长期 Wiki，而不是当前导入切片；acceptance: 多领域仓库首次只导入一个子域时不会把仓库永久命名为该子域，含义不清时在 Init 前解决；owner/method: engineering，Skill contract 与前向测试；provenance: sofa-wiki 初始化为 `sofa4` 的评测发现。
- R28 — Apply 前必须检查完整 staged semantic diff，面向用户的完成说明使用普通语言；acceptance: Maintainer 明确检查 targets、citations、coverage、uncertainty、links，最终报告可用知识和剩余工作，不倾倒协议术语；owner/method: engineering，Skill contract 与前向测试；provenance: 被评测会话跳过 56 次 staged diff 且用户追问 W240 的证据。
- R29 — 已初始化 Wiki 的 compiled Query 必须可由只有项目说明和文件读取能力、没有 Plugin、Shell 或脚本执行能力的 Agent 使用；acceptance: 新仓库包含自足的 `AGENTS.md`，Claude Code 通过薄 `CLAUDE.md` 加载同一契约，代表性问题能从索引和 Concept 得到带引用回答或诚实知识缺口；owner/method: engineering，静态文件检查与跨能力前向测试；provenance: 用户于 2026-08-21 明确指出 Wiki 将交给不具备脚本能力的 Agent。
- R30 — Code Wiki 必须是基础 Wiki 完成后的独立、显式、可选阶段；acceptance: 未提供代码仓库或未调用 `ad-code-wiki` 时现有 Init/Ingest/Query/Lint 行为不变，Plugin 升级不自动扫描；owner/method: engineering，回归与 byte-diff；provenance: 用户于 2026-08-22 明确要求解耦。
- R31 — `ad-code-wiki` 必须自动枚举并评估全部基础 Concept，用户不逐页选择；acceptance: 每页得到 `enriched | docs-only | no-code-match | needs-review | failed`，`evaluated == inventory_total` 才结束评估，pending 不可静默遗漏；owner/method: engineering，Runtime/behavior tests；provenance: 用户纠正“不是用户选择，而是 Skill 自动跑全部”。
- R32 — 代码相关 Concept 必须形成可独立阅读的实现 Companion；acceptance: 包含基础页链接、文档契约、当前实现原理、必要 Mermaid、真实核心代码、revision/path/symbol、相关测试源码及未执行声明、文档—代码关系和不确定性；owner/method: engineering，模板/静态/前向验收；provenance: 用户对局部 Code Wiki 的明确期望。
- R33 — 一次 Code Wiki run 只读取一个用户显式提供的 latest clean Git code repo，并绑定完整 commit SHA；acceptance: code repo 不被修改或执行，dirty/unborn/symlink escape 被拒绝，Prepare/Checkpoint/Finalize 发现漂移即停止；owner/method: engineering，Git fixture 和 byte/status 对比；provenance: 用户只提供最新代码的约束。
- R34 — Code Wiki 必须 checkpoint 全库进度并在全部 Concept 终态后一次原子 Apply；acceptance: 中断保留 run state、不改变 live Bundle，Finalize 冻结 exact staged set，Apply 继续使用 baseline/lock/validation/rollback；owner/method: engineering，transaction/recovery tests；provenance: 全库自动运行与基础 Wiki 故障隔离要求。
- R35 — 文档代表对外契约，代码代表当前实现；Code Wiki 可以反馈问题但不得静默纠正文档；acceptance: 同一 run 只添加 Companion、代码快照摘要和托管实现链接，语义修复需独立授权 Writeback；owner/method: engineering，Skill contract、managed-block 与负向测试；provenance: 用户确认大部分文档可靠并要求冲突备注与可控修复。
- R36 — AD Wiki 不得依赖、调用或消费 Graphify；acceptance: Runtime/package/CLI/Skill/测试无 Graphify import、dependency 或 artifact contract，公开研究只作为设计来源；owner/method: engineering，dependency/static checks；provenance: 用户明确“ad-wiki 不依赖它”。
- R37 — `1.5.0` 必须以显式 `--structural-index` 提供 Java/SOFA-first 结构模式，并保持 `1.4.0` model-only 默认兼容；acceptance: structural mode 使用 Plugin-owned locked `tree-sitter 0.25.2`/`tree-sitter-java 0.23.5` 环境，缺依赖 fail closed，无 flag 不 import/启动 structural Runtime；owner/method: engineering，dependency/compat integration tests；provenance: 用户认可 Java-first 与直接 tree-sitter 依赖。
- R38 — 结构图必须使用稳定大小写敏感 symbol ID、schema validation 和 `EXTRACTED | INFERRED | AMBIGUOUS` relation evidence；acceptance: Java/POM/Properties fixtures、ID property tests、dangling/duplicate/invalid evidence negative tests通过；owner/method: engineering，deterministic unit tests；provenance: Graphify 调研中用户要求吸收的证据与身份能力。
- R39 — 结构索引必须提供 content cache、manifest-last atomic publish、增量 add/change/delete/prune、全局重解引用和可删除重建恢复；acceptance: no-op cache hit、version miss、corrupt cache、failure injection、checkout/worker determinism tests通过；owner/method: engineering，cache/integration tests；provenance: 用户要求设计一个不依赖 Graphify 的吸收迭代。
- R40 — Runtime 必须提供 bounded search/explain/path/BFS/DFS/affected 和 Concept↔symbol bindings；acceptance: code_refs v2 与 graph revision/ID/relation/location一致，Apply success 后才发布 bindings，changed symbol 能选择受影响 Concept，无法证明时回退全评估；owner/method: engineering，query/impact/Code Wiki journey；provenance: 用户认可吸收 Graphify 可借鉴的导航与影响能力。
- R41 — Structural artifacts 只是本地可重建导航视图，不改变 Wiki 真源和治理；acceptance: cache 自忽略、不进 Bundle，不生成社区/God Node Wiki、不 fuzzy merge、不写 Query log、不自动反馈/纠正、不执行 code repo；owner/method: engineering，byte/status/security negative tests；provenance: 已确认 Concept-first、文档优先和受控 Writeback 边界。

## In scope

- 双宿主 AD-Wiki Plugin、三个 canonical Skills 和共享安全 Runtime；
- 初始化仓库中的 canonical `AGENTS.md` 静态 Query 契约及薄 `CLAUDE.md` 兼容入口；
- 单仓库 Init、Ingest、Query、Writeback、Lint、Migrate；
- 一个显式 Wiki + 一个固定 SHA 只读 Git code repo 的全库自动 Code Wiki workflow；
- `wiki/implementations/` Companion、代码快照 Source Summary、托管实现链接、coverage/checkpoint 与 feedback；
- 显式 structural mode 的 Java/POM/Properties extractor、结构图、cache/manifest、bounded query/affected 和 validated bindings；
- 模型通过索引、Markdown 链接和 repository-local text search 直接导航 Wiki；
- 相关 Concept provenance 限定的有界 Raw fallback；
- Raw 注册、哈希和不可变保护；
- 精确 write set、baseline、锁、回滚、校验、可选 Review、Index 和 Log；
- 内容语言、标准 Markdown 链接、来源 coverage 和完成质量说明；
- OKF `0.2`、AD-Wiki Profile `0.1` 及明确注册的未来迁移；
- Git Diff、Commit 和 PR 作为团队审查与恢复边界。

## Out of scope

- BM25、bigram、长度归一化、向量检索、重排或任何预先建立的查询索引；
- Search MCP、Query HTTP API、中央服务、跨库搜索和中央 Bundle Catalog；
- Management App、组织身份、ACL、OAuth Server 或用户目录；
- 服务端 Connector、队列、通用批量导入 Coordinator 和自动 PR；
- Attested Runtime、通用代码执行和外部计算凭据；
- 自动迁移团队仓库、自动合并 PR、全量 Raw 搜索或无条件 Raw 注入；
- 除显式单 code repo 的 Code Wiki workflow 外，其他本地批量导入器和通用跨仓库检索。
- Graphify dependency/artifact、首版多语言 extractor 矩阵、community/God Node 页面、代码 fuzzy merge、Graph UI、watcher/daemon 和 Query 自学习日志。

## Constraints and confirmed decisions

- Markdown/OKF Bundle 和 Git 始终是知识真源。
- 模型拥有语义检索、页面选择和综合；确定性 Runtime 只拥有仓库边界、Raw 完整性、事务、回滚、结构和引用校验。
- 每个知识库独立保存内容、少量领域配置和最小静态 Query 契约，不保存完整 Plugin Prompt、模型检索结果或运行时 host memory。
- 新仓库不生成 `review`、`search.provider` 或 `mcp_threshold_pages` 配置；旧 mapping 可被忽略读取，但不会影响行为。
- Query、Maintainer 与 Code Wiki 不建立 Skill-to-Skill 运行依赖；三个 Skill 只共享确定性 Runtime 和 Bundle 约定。
- 普通 Query 信任编译后的 Bundle；仅窄范围 cache miss 使用受控 Raw fallback。
- compiled Query 的最低能力基线是读取项目说明和 Markdown 文件；Shell、脚本、Plugin 与 Raw fallback 都是可选增强。
- 当前 Profile 保持 `0.1`，本次 Plugin API 删除不触发知识仓库迁移。
- Code Wiki 生成物仍是普通 OKF Concept；运行状态和可重建 structural cache 位于 `.ad-wiki/`，因此 Plugin `1.5.0` 不改变 OKF/Profile。
- Structural mode 显式 opt-in；无 flag 时保持 model-only，缺 AST 环境不得静默降级后继续同一 run。

## Delegated engineering defaults and boundaries

- 工程可以选择最小、本地、可逆的文件布局和测试 fixture，但不得重新引入检索抽象或兼容层。
- 工程可以加强路径、事务、Lint、索引和安全校验，只要不引入远程依赖或新的用户可见审批流程。
- legacy `approve_run.py` 和隐藏 `--owner` 可保留一版非写入 shim，以保护已存在事务和脚本；这不构成已删除 Query API 的兼容承诺。
- 除 R33 明确授权的单一只读 code repo 输入外，任何远程服务、MCP、App、Connector、后台 Worker、跨 Wiki 能力或外部计算权限需要新的 Product Contract。

## Open product decisions

当前范围内无开放产品决策。千页级 BM25、通用本地批量导入、历史源码版本比较、多语言 structural extractor、Graph UI 和中央平台均为明确延期事项。
