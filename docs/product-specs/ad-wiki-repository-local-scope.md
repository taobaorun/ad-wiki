# Product Contract: AD-Wiki 仓库本地 Wiki 构建能力

Authority: 用户于 2026-08-16 确认仓库本地产品定位；于 2026-08-19 删除本地前置审批；于 2026-08-20 确认千页以内由模型直接导航 Wiki，完整删除 Discovery/Hydration/Context Builder，不保留兼容入口

Product Context: 本文同时记录当前版本的持久产品边界。

## Actor and observable outcome

团队成员通过统一分发的 AD-Wiki Plugin，在自己有权访问的单个 Git 仓库中，把不可变 Raw Sources 持续编译为可读、可追溯、可审查的 OKF Wiki。

用户安装 Plugin 后，可以在不依赖 AD-Wiki 中央服务的情况下完成初始化、来源登记、Ingest、只读 Query、Writeback、Lint、Migrate，以及 baseline-bound、可校验、失败可回滚的知识写入事务。模型直接使用 Wiki 的索引、链接和 Markdown 内容，不在阅读前经过 AD-Wiki 自建的相关性过滤层。

## Requirements

- R1 — AD-Wiki 以可复用 Plugin、Skill 和确定性脚本分发能力，不集中保存团队知识；acceptance: Plugin 包不包含具体团队知识或凭据；owner/method: engineering，发行物检查；provenance: 用户对“AD-Wiki 只提供能力”的确认。
- R2 — 每次操作显式绑定一个仓库根，不能扫描、检索或修改其他知识库；acceptance: 双仓库隔离测试中操作 A 后 B 字节不变；owner/method: engineering，自动化测试；provenance: 仓库本地边界。
- R3 — `raw/` 是不可变事实输入，`wiki/` 是 OKF Bundle，`.ad-wiki/` 保存 Bundle 外的本地运行状态；acceptance: Raw Guard、Bundle 校验和路径边界测试通过；owner/method: engineering，自动化测试；provenance: LLM-Wiki 与 OKF。
- R4 — 核心闭环不依赖远程 AD-Wiki 服务；acceptance: 断网时本地 Init、Ingest、Query、Writeback、Lint 和 Migrate 仍可执行；owner/method: engineering，本地端到端测试；provenance: 当前产品定位。
- R5 — 当前版本不提供 Search MCP、BM25、向量检索、重排、中央索引或跨仓库检索；acceptance: Manifest 不声明相关能力，代码不包含未启用搜索配置或索引；owner/method: engineering，发行物检查；provenance: 用户于 2026-08-20 明确延期到真实千页级瓶颈后再评估。
- R6 — 当前版本不提供管理 App、组织身份、中央 ACL 或服务端审批台；acceptance: Plugin 不声明 App，权限和 Git Review 由现有团队系统负责；owner/method: engineering，发行物检查；provenance: 用户明确排除。
- R7 — 当前版本不提供服务端批量导入、Connector 调度、中央队列或跨仓库 Batch；acceptance: 无 Worker、Connector 凭据或中央 Batch 状态；owner/method: engineering，代码检查；provenance: 用户明确排除。
- R8 — 当前版本不提供 Attested Runtime；acceptance: 可读取 `Attested Computation`，但无 Executor、Attester 或 Receipt Store；owner/method: engineering，Profile 测试；provenance: DR-001。
- R9 — 未来中央平台设计不能为当前实现扩张授权；acceptance: 当前交付不依赖未来平台；owner/method: product/design owner，文档审查；provenance: 当前本地范围。
- R10 — 同一发行仓库能被 Codex 和 Claude Code 的原生 Plugin/Marketplace 发现；acceptance: 仓库根为唯一 Plugin 根，两端 Manifest/Marketplace 指向 `./`；owner/method: engineering，打包与安装验证；provenance: 双端兼容要求。
- R11 — 双端兼容不得复制两套 Maintainer、Query 或 Runtime；acceptance: 每个 Skill 只有一个 canonical 实现，宿主差异仅在薄 Manifest；owner/method: engineering，发行物检查；provenance: 统一分发要求。
- R12 — 两个宿主遵守相同仓库边界、Raw 不可变、引用和直接 Apply 事务规则；acceptance: 双宿主前向测试覆盖 Init、只读 Query 和一次 `prepare → apply` 写入；owner/method: engineering，前向测试；provenance: 双端兼容与直接 Apply 决策。
- R13 — 两个 Manifest 使用相同 Plugin 名和正式 SemVer；acceptance: 名称均为 `ad-wiki`、版本完全一致且无正式 cachebuster；owner/method: engineering，打包测试；provenance: 可升级性要求。
- R14 — 仓库根直接作为 Plugin 根，Skill 位于根级 `skills/`；acceptance: 无 `plugins/ad-wiki` 包装层；owner/method: engineering，目录测试；provenance: 已确认发行结构。
- R15 — 仓库本地写入不要求或生成前置审批；`apply_run.py` 直接消费完整 staged write set，并在锁内执行 baseline、Raw、路径、校验和回滚保护；acceptance: low/medium/high 新事务均可从 `PLANNED` Apply，旧批准事务仍校验已有 staged hash，`approve_run.py` 兼容 shim 不记录 actor 或改变状态；owner/method: engineering，状态机与负向测试；provenance: 用户于 2026-08-19 删除审批。
- R16 — Init 持久化内容语言，默认 `zh-CN`，允许 `en`；acceptance: 配置、Index、Log 和 Agent 生成内容遵循语言，Raw 与代码不翻译；owner/method: engineering，端到端测试；provenance: 用户确认。
- R17 — 面向用户的 Query 由独立只读 `ad-wiki-query` Skill 提供；acceptance: Query Skill 不呈现写命令，Maintainer 不公开普通问答；owner/method: engineering，Skill contract；provenance: 用户确认职责边界。
- R18 — 千页以内的 Query 和 Maintainer 影响分析由模型直接渐进导航 Wiki；acceptance: Skill 先读配置和索引，再以 `rg` 或宿主等价能力搜索 Bundle Markdown、读取模型判断相关的完整页面，并可迭代关键词；不存在固定 Top-K、score threshold 或 pre-model 字符预算；owner/method: engineering，Skill contract 与真实问题前向测试；provenance: 用户于 2026-08-20 明确“完全信任模型检索，不要提前过滤”。
- R19 — `search_wiki.py`、`build_query_context.py`、builtin scorer、Discovery Catalog、Hydration/Context Envelope 及其公开 API 必须完整删除且不保留兼容入口；acceptance: 活跃代码、脚本、Skill 和测试不包含这些入口；owner/method: engineering，静态和打包测试；provenance: 用户于 2026-08-20 明确不需要兼容。
- R20 — Query 保持只读并信任已经编译的 Wiki；acceptance: 正常命中只读取 Bundle，不运行事务、全量健康检查或 Raw Guard，查询前后仓库字节不变；owner/method: engineering，Skill contract 与字节对比；provenance: LLM-Wiki“编译一次、持续复用”。
- R21 — Wiki 缺少一个窄事实、但已读 Concept 明确声明登记来源时，可执行一次有界 Raw fallback；acceptance: fallback 由 Concept ID 限定来源、校验所读 Raw 哈希、不扫描全部 Raw、不写回，并在回答中区分 compiled knowledge 与 Raw；owner/method: engineering，CLI 和边界测试；provenance: 用户接受受控 cache miss。
- R22 — 超过约 1000 页只是重新评估 BM25 的触发条件，不是当前配置或自动路由；acceptance: 新仓库不写 search provider/threshold，文档不承诺自动切换；owner/method: product/engineering，配置和文档检查；provenance: 用户于 2026-08-20 明确延期。
- R23 — Query 默认回答简洁、可移植，只在影响结论时披露证据边界；acceptance: 使用仓库相对 Concept 路径和 source ID，不输出绝对路径、搜索命令或内部遥测；owner/method: engineering，Skill contract 与前向测试；provenance: 用户反馈与跨宿主要求。
- R24 — Maintainer 把长 FAQ、教程和多主题来源编译成可独立回答的原子 Concept；acceptance: Source Summary 只承担 provenance 目录作用，`coverage: full` 仅在读完整来源后使用，partial 必须披露范围且导入不得报告完成；owner/method: engineering，模板、Lint 和行为测试；provenance: sofa-wiki 评测。
- R25 — Wiki 内部关系使用标准 Markdown Bundle 链接；acceptance: 模板和 Skill 禁止 `[[wikilinks]]`，Validator 报告不支持语法与不存在目标；owner/method: engineering，验证测试；provenance: sofa-wiki 中 284 个不可识别链接的评测证据。
- R26 — Maintainer 和 Query 不得把工作结果写入目标仓库外的 host memory、`CLAUDE.md`、`AGENTS.md` 或全局配置，除非用户显式要求；acceptance: Skill contract 明确，前向执行目标外字节不变；owner/method: engineering，行为测试；provenance: 被评测会话的两次外部 memory 写入。
- R27 — `domain` 描述整个长期 Wiki，而不是当前导入切片；acceptance: 多领域仓库首次只导入一个子域时不会把仓库永久命名为该子域，含义不清时在 Init 前解决；owner/method: engineering，Skill contract 与前向测试；provenance: sofa-wiki 初始化为 `sofa4` 的评测发现。
- R28 — Apply 前必须检查完整 staged semantic diff，面向用户的完成说明使用普通语言；acceptance: Maintainer 明确检查 targets、citations、coverage、uncertainty、links，最终报告可用知识和剩余工作，不倾倒协议术语；owner/method: engineering，Skill contract 与前向测试；provenance: 被评测会话跳过 56 次 staged diff 且用户追问 W240 的证据。

## In scope

- 双宿主 AD-Wiki Plugin、两个 canonical Skills 和共享安全 Runtime；
- 单仓库 Init、Ingest、Query、Writeback、Lint、Migrate；
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
- 服务端 Connector、队列、批量导入 Coordinator 和自动 PR；
- Attested Runtime、通用代码执行和外部计算凭据；
- 自动迁移团队仓库、自动合并 PR、全量 Raw 搜索或无条件 Raw 注入；
- 本轮未授权的本地批量导入器。

## Constraints and confirmed decisions

- Markdown/OKF Bundle 和 Git 始终是知识真源。
- 模型拥有语义检索、页面选择和综合；确定性 Runtime 只拥有仓库边界、Raw 完整性、事务、回滚、结构和引用校验。
- 每个知识库独立保存内容与少量领域配置，不保存 Plugin Prompt、模型检索结果或 host memory。
- 新仓库不生成 `review`、`search.provider` 或 `mcp_threshold_pages` 配置；旧 mapping 可被忽略读取，但不会影响行为。
- Query 与 Maintainer 不建立 Skill-to-Skill 运行依赖。
- 普通 Query 信任编译后的 Bundle；仅窄范围 cache miss 使用受控 Raw fallback。
- 当前 Profile 保持 `0.1`，本次 Plugin API 删除不触发知识仓库迁移。

## Delegated engineering defaults and boundaries

- 工程可以选择最小、本地、可逆的文件布局和测试 fixture，但不得重新引入检索抽象或兼容层。
- 工程可以加强路径、事务、Lint、索引和安全校验，只要不引入远程依赖或新的用户可见审批流程。
- legacy `approve_run.py` 和隐藏 `--owner` 可保留一版非写入 shim，以保护已存在事务和脚本；这不构成已删除 Query API 的兼容承诺。
- 任何远程服务、MCP、App、Connector、后台 Worker、跨仓库能力或外部计算权限需要新的 Product Contract。

## Open product decisions

当前范围内无开放产品决策。千页级 BM25、本地批量导入和中央平台均为明确延期事项。
