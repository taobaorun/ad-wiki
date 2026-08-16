# Product Contract: AD-Wiki 仓库本地 Wiki 构建能力

Authority: 用户于 2026-08-16 明确确认当前产品定位
Product Context: 本文同时记录当前版本的持久产品边界

## Actor and observable outcome

团队成员通过统一分发的 AD-Wiki Plugin，在自己有权访问的单个 Git 仓库中，把不可变 Raw Sources 持续编译为可读、可追溯、可审查的 OKF Wiki。

用户安装 Plugin 后，可以在不依赖 AD-Wiki 中央服务的情况下完成初始化、来源登记、Ingest、Query、Writeback、Lint、Migrate、本地搜索以及受门禁的知识写入事务。每个团队知识库独立保存内容、配置、权限和 Git 历史。

## Requirements

- R1 — AD-Wiki 以可复用 Plugin/Skill/确定性脚本的形式分发能力，不集中保存团队知识；acceptance: Plugin 包不包含具体团队知识或凭据；owner/method: engineering，检查发行物与两个独立样例仓库；provenance: 用户关于“AD-Wiki 只是提供能力”和团队分发的确认。
- R2 — 每次操作显式绑定一个仓库根目录，不能扫描、检索或修改其他知识库；acceptance: 双仓库隔离测试中操作 A 后 B 字节不变；owner/method: engineering，自动化测试；provenance: 已接受的团队工作流边界。
- R3 — `raw/` 是不可变事实输入，`wiki/` 是仓库内的 OKF Bundle，`.ad-wiki/` 保存 Bundle 外的本地运行状态；acceptance: Raw Guard、Bundle 校验和目录边界测试通过；owner/method: engineering，自动化测试；provenance: LLM-Wiki、OKF 与当前 v0.2 实现。
- R4 — 核心 Wiki 构建与维护闭环不依赖远程 AD-Wiki 服务；acceptance: 断网或没有中央配置时，本地 Init、Ingest、Query、Writeback、Lint 和 Migrate 仍可执行；owner/method: engineering，本地端到端测试；provenance: 用户于 2026-08-16 的产品定位确认。
- R5 — 当前版本不提供集中式 Search MCP、Fleet Catalog、中央索引或跨仓库检索；acceptance: Plugin Manifest 不声明远程 Search MCP，查询只能使用当前仓库 builtin search；owner/method: engineering，Manifest 与行为测试；provenance: 用户于 2026-08-16 的明确排除。
- R6 — 当前版本不提供管理 App、组织身份接入、中央 ACL 或服务端审批台；acceptance: Plugin 不声明 App，仓库权限和 Git Review 仍由现有团队系统负责；owner/method: engineering，发行物检查；provenance: 用户于 2026-08-16 的明确排除。
- R7 — 当前版本不提供服务端批量导入、Connector 调度、中央队列或跨仓库 Batch；acceptance: 没有服务端 Worker、Connector 凭据或中央 Batch 状态；owner/method: engineering，代码与发行物检查；provenance: 用户于 2026-08-16 的明确排除。
- R8 — 当前版本不提供 Attested Runtime；acceptance: 可以读取和校验 `Attested Computation` Concept，但不存在 Executor、Attester、Receipt Store 或计算类 MCP Tool；owner/method: engineering，Profile 与发行物测试；provenance: 用户确认的 DR-001。
- R9 — 尚未实现的中央平台设计只能作为未来研究材料，不能为实现、权限、部署或依赖扩张提供当前授权；acceptance: 当前 ImplementationPlan 不引用中央平台能力作为交付要求；owner/method: product/design owner，文档审查；provenance: 用户于 2026-08-16 的产品定位确认。
- R10 — 同一个 AD-Wiki 发行仓库必须能被 Codex 和 Claude Code 各自的原生 Plugin/Marketplace 机制发现和安装；acceptance: 仓库根就是唯一 Plugin 根，两端官方校验器通过，两个 Marketplace 都以 `./` 解析到该根目录，并在隔离环境完成发现与安装冒烟测试；owner/method: engineering，自动化与 CLI 验证；provenance: 用户于 2026-08-16 提出的双端兼容要求及单 Plugin 仓库扁平化确认。
- R11 — 双端兼容不得复制两套维护提示词或 Runtime；acceptance: 仓库只有一个 canonical `ad-wiki-maintainer/SKILL.md`、一套 references 和一套确定性脚本，宿主差异仅存在于薄 Manifest、Marketplace 元数据和必要的路径解析说明；owner/method: engineering，发行物检查；provenance: 既有“知识库只保存内容与少量领域配置”原则及本次双端分发要求。
- R12 — Codex 与 Claude Code 对同一知识库执行相同操作时必须遵守同一套仓库边界、审批门禁、Raw 不可变、引用和事务规则；acceptance: 双宿主前向测试覆盖 Init、只读 Query 和一次受门禁写入，输出的仓库结构与校验结果符合相同契约；owner/method: engineering，双宿主前向测试；provenance: 本次兼容要求。
- R13 — 双端 Plugin 使用同一个稳定插件名和发布版本；acceptance: 两个 Plugin Manifest 的 `name` 均为 `ad-wiki`，正式发布时 SemVer 完全一致，版本不一致会阻断打包测试；owner/method: engineering，Manifest contract test；provenance: 团队统一分发与可升级性要求。
- R14 — AD-Wiki 作为单 Plugin 仓库时，仓库根必须直接作为 Plugin 根，Skill 统一放在可扩展的根级 `skills/`；acceptance: 仓库不存在 `plugins/ad-wiki` 包装层，两个 Marketplace source 均为 `./`，新增并列 Skill 不需要修改 Plugin 根或复制 Runtime；owner/method: engineering，目录与 packaging contract test；provenance: 用户于 2026-08-16 参考真实 Plugin 仓库后确认的发行结构。
- R15 — `review.owners` 只作为高风险事务的真实 human 事前审批白名单；acceptance: 空 owner 列表不影响低风险或中风险工作流，但高风险 Apply 必须失败并给出可操作提示；非空时只有列出的 `human:<id>` 可以批准高风险事务；中风险仍由任意具名 human 完成事后 Review，不被 owner 白名单限制；owner/actor 身份由现有 Git/PR 权限系统负责，AD-Wiki 不宣称完成认证；owner/method: engineering，状态机、CLI 与策略测试；provenance: 用户于 2026-08-16 接受 owner 推荐语义。
- R16 — Init 必须持久化团队 Wiki 的内容语言，默认 `zh-CN`，并允许显式选择 `en`；acceptance: 新仓库配置、初始化说明、Index 与 Log 使用所选语言，后续 Skill 生成的标题、摘要、正文和默认回答遵循该语言；Raw、代码、专有标识和引用原文不翻译；旧仓库缺少字段时按 `zh-CN` 解释但不自动重写已有内容；owner/method: engineering，Init、兼容、模板/Skill 与端到端测试；provenance: 用户于 2026-08-16 接受语言推荐并指定默认值 `zh-CN`。

## In scope

- 团队统一分发、同时支持 Codex 与 Claude Code 原生安装的 AD-Wiki Plugin；
- 两个宿主各自的薄 Plugin Manifest 和 Marketplace Catalog；
- 根级、可扩展的 `skills/` 集合；当前包含 `ad-wiki-maintainer` Skill 和少量仓库领域配置；
- 单仓库 Init、Ingest、Query、Writeback、Lint、Migrate；
- builtin repository-local search；
- Raw Source 注册、哈希和不可变保护；
- 精确 write set、baseline、审批、锁、回滚、校验、Review、Index 和 Log；
- 可选初始化 owner、高风险 owner 门禁，以及不依赖 AD-Wiki 身份系统的具名 human 审计记录；
- 初始化时持久化内容语言，当前支持 `zh-CN` 与 `en`；
- OKF `0.2` 与 AD-Wiki Profile 的兼容、校验和未来本地迁移；
- Git Diff、Commit 和 PR 作为团队内容变更的审查与恢复边界。

## Out of scope

- AD-Wiki 托管的中央服务或控制平面；
- 集中式 Search MCP、跨库搜索和中央向量索引；
- Management App、Fleet Dashboard 和组织身份系统；
- 中央 Bundle Catalog、ACL、OAuth Server 或用户目录；
- 服务端 Connector、作业队列、批量导入 Coordinator 和自动 PR 服务；
- Attested Runtime、通用代码执行、数据仓库凭据、Receipt/Verdict；
- 自动迁移所有团队仓库、自动合并 PR 或修改默认分支；
- AD-Wiki 自建身份认证、把 actor 字符串宣称为已认证身份、自动翻译 Raw 或批量改写既有 Wiki；
- 本轮没有明确要求的本地批量导入器。

## Constraints and confirmed decisions

- Markdown/OKF Bundle 和 Git 始终是知识真源；索引或工具输出不能替代它们。
- 每个知识库独立保存内容和少量领域配置，不复制整套提示词。
- 仓库根就是双宿主共享的唯一 Plugin 根；所有 Skill 位于根级 `skills/`，当前包含 `ad-wiki-maintainer`，未来可以继续新增 Skill，而宿主 Manifest 不承载维护流程正文。
- Plugin 不保存具体团队知识、访问令牌或组织权限数据。
- 本地搜索故障不能影响人直接读取 Markdown。
- 当前 Plugin 可以理解 `Attested Computation` 内容类型，但不得暗示具备执行或 Attestation 能力。
- 规模化平台设计是未来备选，不属于当前版本承诺。
- 双宿主兼容只承诺原生发现、安装和相同核心工作流；不因此引入 Claude Code 专属 Agent/Hook、Codex App/MCP 或其他宿主专属产品能力。
- `review.owners` 为空表示尚未授予高风险审批权，不表示知识库不可用；owner 必须是 `human:<id>`，且只限制高风险事前审批。
- 中风险事务仍需要明确写入授权和真实 `human:<id>` 事后 Review；配置 owner 不把日常 Ingest Review 集中到 owner。
- 内容语言默认 `zh-CN`；它约束 Agent 生成的知识表达，不改变 Raw、代码、引用、稳定标识或已有文件路径。

## Delegated engineering defaults and boundaries

- 工程可以在不改变行为契约的前提下选择本地、可逆的文件布局、Python helper、测试 fixture 和性能优化。
- 工程可以加强当前仓库内的路径、事务、Lint、索引和安全校验，只要不引入远程依赖或新的用户可见流程。
- 工程可以选择最小的配置字段和 CLI 参数表达 owner 与内容语言，只要保持向后兼容、错误可操作，且不把 actor 字符串提升为认证机制。
- 任何远程服务、MCP Server、App、组织身份、Connector、后台 Worker、跨仓库能力或外部计算权限都超出默认授权，必须获得新的 Product Contract。
- 本地批量导入若未来提出，必须仍以一个目标仓库、每来源可追溯、Raw 不可变和现有事务门禁为基础，并单独确认其用户体验和自动化等级。

## Open product decisions

当前边界内无开放产品决策。中央平台、服务端能力和本地批量导入均为明确延期事项，不是当前实现者需要解决的问题。
