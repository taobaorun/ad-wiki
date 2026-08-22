# Product Contract: AD Wiki Read-Only Skill Delivery

Authority: 用户于 2026-08-23 确认把已经构建完成的 Wiki 交付为单个独立 Skill；Skill 名称使用 `ad-${wiki-name}`，例如 `sofa-wiki` 生成 `ad-sofa-wiki`；交付物只负责本地构建，不负责远程部署；必须包含完整只读 Query 与 Primary Source fallback；Writeback、会话采集和异步知识回流延期讨论。

Product Context: not-available；本合同是独立的新任务权威，不修改既有构建、维护或 Code Wiki Product Contract。

## Actor and observable outcome

AD Wiki 的构建者在一个 Wiki 完成 Ingest、可选 Code Wiki 和校验后，把它转换成一个可安装、可复制、不可变的只读知识 Skill。下游用户只需安装并调用 `ad-${wiki-name}`，无需理解 AD Wiki 的构建目录、runs、Plugin 或维护流程，即可使用完整 compiled Query、引用和登记 Raw fallback。

## Requirements

- R-SD1 — 首版采用“一份 Wiki 生成一个 Skill”；acceptance: 每个构建输入只产生一个独立 Skill 根，不生成多 Wiki 聚合包或跨 Wiki 路由；owner/method: engineering，packaging journey；provenance: 用户明确“先支持按单 skill 方式交付”。
- R-SD2 — Skill 名称必须为 `ad-${wiki-name}`；`sofa-wiki` 必须生成 `ad-sofa-wiki`；acceptance: 名称符合 Skill 的 lowercase/digit/hyphen 约束，输出目录、Skill frontmatter 和 manifest 名称一致，无法无歧义规范化或发生冲突时构建失败；owner/method: engineering，name property/negative tests；provenance: 用户明确命名规则。
- R-SD3 — `wiki-name` 是显式交付身份；工程可在未显式提供时使用输入仓库 basename 作为可逆默认，但不得用 domain title、目录内容或模型推断改名；acceptance: 显式名称优先，默认来源和规范化结果在构建报告中可见；owner/method: engineering，CLI/API tests；provenance: 用户用 `sofa-wiki` 仓库名定义期望 Skill 名。
- R-SD4 — 交付边界止于生成本地 Skill 目录和可选传输归档；acceptance: 构建不上传服务器、不推送镜像、不调用 SSH/Kubernetes/CDN、不切流、不申请部署凭据；owner/method: engineering，package/static/security checks；provenance: 用户确认“只生成交付包”。
- R-SD5 — 交付 Skill 必须保持完整只读 Query：Index/ToC 导航、完整 Concept 阅读、标准引用、来源/快照披露、登记 Raw Primary Source fallback、知识缺口和冲突诚实表达；acceptance: 代表性 compiled hit 与 Raw fallback 问题均可由交付 Skill 回答，回答使用包内相对 Concept 路径和 source ID；owner/method: product/engineering，fresh-agent journeys；provenance: 用户确认“需要完整能力”并将本次收敛到正常 Query。
- R-SD6 — Query 不能依赖脚本能力；acceptance: 只有 Skill 指令和文件读取/搜索能力的 Agent 能导航 Wiki，并能通过包内 Source Registry 精确读取一个相关 Raw 文档/章节；有命令执行能力时可使用打包的确定性只读 helper，但 helper 缺失或不可执行不能阻断 compiled Query；owner/method: engineering，双能力前向测试；provenance: AD Wiki 既有无脚本 Agent 要求和用户对完整 Raw fallback 的确认。
- R-SD7 — 交付 allowlist 必须包含 Skill 入口、完整 OKF `wiki/`、`ad-wiki.yaml`、静态只读 Query 契约、Source Registry、其登记的全部 Raw bytes、必要的可选领域只读 metadata、artifact manifest，以及实现 R-SD5/R-SD6 所需的只读 helper/reference；acceptance: manifest 能枚举每个交付文件及其 digest，Bundle 中声明的来源能解析到包内登记证据；owner/method: engineering，manifest/source-closure tests；provenance: 用户要求按 Skill 交付完整 Query/Raw 能力。
- R-SD8 — 未登记 Raw、构建工作区中的其他文件和跨仓库内容不得因目录共存被带入；acceptance: 交付 Raw 集合等于 Source Registry 声明并通过路径/哈希校验的集合，额外 Raw、symlink escape 和输入仓库外文件使构建失败或保持排除且报告；owner/method: engineering，path/source negative tests；provenance: Primary Source provenance 和单 Wiki 边界。
- R-SD9 — `.ad-wiki/runs/`、staged bytes、cache、lock、临时 assessment、Query 历史、构建日志和本机绝对路径不得进入交付 Skill；acceptance: 递归 artifact inspection 无这些路径或内容，已有 15 个 validated runs 的真实 Wiki fixture 也不会把 run state 打包；owner/method: engineering，real/fixture package inspection；provenance: 用户确认 runs 是构建期状态，线上只读交付不需要。
- R-SD10 — 交付 Skill 不包含 Ingest、Writeback、Apply、Review、Migrate、Code Wiki 构建或任何 live Wiki 修改入口；acceptance: Skill 指令和工具面只有只读 Query/验证行为，交付目录 byte-diff 测试证明代表性 Query 前后不变；owner/method: engineering，static/behavior tests；provenance: 用户将首版收敛到正常 Query，Writeback 后续讨论。
- R-SD11 — 构建前必须验证 Bundle/Profile、Source Registry 和全部交付 Raw 哈希；acceptance: invalid Bundle、缺失/变化/越界 Raw、损坏静态入口或无法闭合的引用使构建失败，且不产生可被误认成成功的最终 Skill；owner/method: engineering，validator/transactional negative tests；provenance: AD Wiki correctness gates 与 Primary Source 完整性。
- R-SD12 — 高置信凭据、私钥或敏感文件名不得被静默打入交付物；acceptance: private-key material、已知 credential patterns 和禁止文件名使构建失败并只报告相对路径/类别，不回显秘密；普通内部知识内容不被未经授权上传或集中分析；owner/method: security/engineering，secret fixtures 与 output inspection；provenance: 完整 Raw 交付扩大分发半径，需要 fail-closed 凭据边界。
- R-SD13 — 每个交付 Skill 必须是绑定输入快照的不可变产物；acceptance: artifact manifest 至少记录 artifact schema、wiki/skill name、AD Wiki Plugin/Profile/OKF 版本、可用 Git revision、Bundle digest、Source Registry digest、逐文件 digest、文件/来源/Concept 数量及交付能力声明；owner/method: engineering，schema/digest tests；provenance: 可复制部署和快照透明要求。
- R-SD14 — 相同输入快照和相同构建选项必须产生相同内容清单与 artifact digest；acceptance: 跨临时目录重复构建的 manifest 内容身份一致，时间、绝对路径和机器信息不参与内容 digest；owner/method: engineering，reproducibility test；provenance: 不可变 Skill 快照和可审计交付要求。
- R-SD15 — 构建必须原子且不修改源 Wiki；acceptance: 先在隔离临时位置完成复制、校验和 manifest，再发布到显式输出目标；失败不留下完整外观的半成品，输入仓库构建前后字节一致；非空冲突目标不得被静默覆盖；owner/method: engineering，fault injection/byte identity tests；provenance: AD Wiki 既有 baseline/atomicity 原则。
- R-SD16 — 交付 Skill 必须保持宿主中立；acceptance: 同一个 canonical Skill 通过 Codex/Claude Skill validator，Skill instructions 不依赖 Plugin 安装路径、源 Wiki 绝对路径或特定服务器；owner/method: engineering，双宿主 packaging/fresh-session tests；provenance: AD Wiki 双宿主单实现原则。
- R-SD17 — 构建结果必须返回普通语言摘要和机器可读报告；acceptance: 包含 Skill 名、输出位置、artifact digest、Wiki/Raw/Concept 计数、包含/排除能力、验证结果、敏感性提示和已知限制，不倾倒 runs 或内部事务状态；owner/method: engineering/product，CLI contract/UX review；provenance: 用户希望交付构建好的 Wiki，而不是理解内部构建过程。
- R-SD18 — Wiki 更新后通过重新构建生成新的不可变 `ad-${wiki-name}` 快照，不在已安装 Skill 内原地维护；acceptance: 新旧 artifact digest 可并存/比较，旧包不会在 Query 时改变；owner/method: engineering，two-revision packaging test；provenance: 用户接受写回原始 Wiki、重建再分发的总体方向，但 Writeback 本次延期。

## In scope

- 新的 `ad-wiki-ship` 构建能力；
- 一个 AD Wiki 到一个只读 Skill 的本地交付；
- `ad-${wiki-name}` 命名与冲突校验；
- 完整 Wiki、登记 Raw、Source Registry 和只读 Query 能力闭包；
- 有脚本/无脚本 Agent 的 compiled Query 与 Raw fallback；
- allowlist、来源闭包、敏感凭据门禁、快照 manifest、digest、可复现和原子输出；
- Codex/Claude 通用 Skill 结构和机器/人类可读构建结果。

## Out of scope

- 上传服务器、镜像构建/推送、CI/CD、SSH、Kubernetes、CDN、切流和回滚部署；
- 多 Wiki 合并成一个 Skill、跨 Wiki Query 或中央 Bundle Catalog；
- Ingest、Writeback、Apply、Review、Migrate、Code Wiki 构建和线上知识修改；
- 会话采集、Query 日志、异步 Writeback 分析、candidate submission Tool/MCP；
- 将 `.ad-wiki/runs/`、cache、lock、assessment 或构建日志作为线上能力；
- 自动发布到 Marketplace、GitHub Release 或其他分发渠道；
- 未登记 Raw、源代码仓库或其他本地目录的隐式打包。

## Constraints and confirmed decisions

- 用户只安装和查询 `ad-${wiki-name}`，不承担 AD Wiki 内部目录或 fallback 模式选择。
- 交付 Skill 是只读、版本化知识快照；源 AD Wiki 始终是持续构建和未来 Writeback 的真源。
- 完整 Raw fallback 会扩大数据分发范围，交付者必须按与 Raw 同等级别控制 Skill 的访问权限。
- Source Registry 与 Raw bytes 必须成套交付；不能只复制 Raw 或只复制来源元数据。
- Skill 不需要 `.ad-wiki/runs/` 才能完成正常 Query；构建侧可以保留 runs 作为审计/恢复信息，但不得复制到 artifact。
- 构建命令对输入 Wiki 和代码仓库均为只读；输出只能写入显式目标。
- 当前工作树中的 `.agents/skills`、本地 stash、其他 worktree 和发布 tag 属于 run context，不进入产品范围或交付包。

## Delegated engineering defaults and boundaries

- Engineering 可选择 Skill 内部目录布局、manifest JSON 字段的机械排序、归档格式、压缩参数、只读 helper 的最小实现和原子发布机制，但不得改变单 Skill、完整 Raw、只读能力或排除项。
- Engineering 可从显式 `wiki-name` 生成合法 Skill 名，并以仓库 basename 作为未显式提供时的默认；任何会改变名称含义或造成冲突的情况必须失败，不得自动加随机后缀。
- Engineering 可用内容 digest、可用 Git revision 和调用方显式分发版本共同标识产物；不得用构建时间或机器路径作为唯一版本身份。
- Engineering 可选择目录或归档作为主要交付形态，但至少必须产生一个标准 Skill 目录，归档只是该目录的传输表示。
- Engineering 可复用现有 Validator、Raw Guard 和高置信 secret patterns；不得为了交付成功绕过失败门禁或提供静默敏感信息 override。

## Open product decisions

无。
