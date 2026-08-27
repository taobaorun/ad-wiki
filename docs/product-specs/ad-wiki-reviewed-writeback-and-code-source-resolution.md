# Product Contract: AD Wiki 分级评审写回与代码源重定位

Authority: 用户于 2026-08-27 基于 Codex 会话 `01a0380b-086f-76b3-90d7-0c93a4da7d46` 的实际 SOFA Wiki writeback 行为提出改进，并通过 `ad-grill` 明确确认：人工二次确认只覆盖 Query 派生的多轮综合或 medium/high-risk 写回；多轮综合自动至少归为 medium-risk；评审采用结构化摘要加可点击的完整 staged diff，用户查看后再独立确认 Apply。用户同时要求持久记录 Code Wiki 关联的代码来源，避免后续会话重复搜索历史记录或工作区。用户随后通过 `ad-align` 接受“自动发现并提示候选、人工触发 staging、人工确认 Apply”的交互方向，并确认复用 Query 与 Maintainer，不新增用户可见 Writeback Skill。

Product Context: not-available；本合同是当前独立行为变更的权威，不修改或继承其他 Product Contract 的未声明要求。

## Actor and observable outcome

使用 AD Wiki 查询领域问题并决定是否沉淀知识的团队成员，不需要记忆新的 Skill：Query 在多轮讨论形成稳定、可复用知识时自动更新并适度提示一个当前 writeback candidate；用户用自然语言决定是否生成 staged candidate，再在看到冻结候选的影响、证据和完整 staged diff 后，通过独立确认触发 live Wiki 修改。低风险简单写回保持当前效率。后续需要源码核实时，Agent 能从 Wiki 持久化的代码来源身份定位已明确关联的本地 worktree，无法安全定位时询问用户，而不是搜索历史会话或扫描工作区。

## Requirements

- R-WB1 — Query 必须保持只读；它可以提出或修订 writeback candidate，但不得创建写事务、修改 live Wiki、Raw、索引、日志或 host memory；acceptance: 普通查询、多轮查询和候选生成前后，目标仓库受保护字节保持不变；owner/method: engineering，Query journey 与 byte-identity 测试；provenance: 用户要求先查询讨论、评审后再真正 writeback，及本轮已确认的 Query/Maintainer 分工。
- R-WB2 — Query 派生的写回只要属于多轮综合或 medium/high-risk，就必须进入二阶段人工确认；acceptance: 对应场景中，第一次“writeback/接受候选”后 live Wiki 不变，系统只产生待评审候选；owner/method: engineering，Claude/Codex 会话回放与事务状态测试；provenance: 用户明确“只覆盖多轮综合或 medium/high-risk”。
- R-WB3 — 多轮综合定义为综合两个以上用户问题或补充事实，或者修正、弱化、推翻本轮较早结论；命中后自动至少归为 medium-risk，不能由 Agent 降级；acceptance: 两类正向场景均进入二阶段确认，单纯改写同一答案格式的反向场景不被误判；owner/method: engineering，分类 fixtures 与会话评测；provenance: 用户明确认可该定义。
- R-WB4 — 对 R-WB2 覆盖的操作，第一次确认只授权 Maintainer 重新导航当前 Wiki、确定影响集并生成冻结 staged candidate，不授权 Apply；acceptance: staging 完成后事务停在可评审状态，`applied_set` 为空且 live Wiki 未变化；owner/method: engineering，事务集成测试；provenance: 用户认可“先源码核实与 staged diff，待确认后才真正 writeback”的交互。
- R-WB5 — Apply 前的评审摘要必须说明受影响页面，新增、修改、弱化或删除的结论，文档/代码证据及 revision，未解决的证据缺口，预验证结果，并提供可点击的 staged 文件或完整 diff；acceptance: 代表性 medium/high 候选的评审输出包含全部字段，链接可打开对应冻结内容；owner/method: engineering + human reviewer，输出契约测试与人工体验验收；provenance: 用户认可“结构化摘要 + staged diff 链接”，并表示需要时会通过链接查看。
- R-WB6 — 用户在评审输出之后发送的独立 `apply/确认写入` 才授权 Apply，且授权只绑定已展示的冻结内容；write set、staged bytes、证据 revision 或影响结论变化后，旧确认失效并必须重新展示、重新确认；acceptance: 未确认 Apply 被拒绝，确认后原样候选可写入，任一受约束内容变化都会恢复到待评审状态；owner/method: engineering，状态机、digest/baseline 与负向并发测试；provenance: 用户认可评审建议，要求真正写入发生在查看候选后的确认。
- R-WB7 — 单轮、low-risk 且已有明确写权限的操作可以在 Agent 检查完整 staged diff 后直接 Apply 和验证，不增加强制二次确认；acceptance: 确定性索引更新、无歧义链接或等价 low-risk fixture 保持单次授权完成；owner/method: engineering，低风险回归测试；provenance: 用户明确二次确认不覆盖所有写回。
- R-WB8 — 本合同不把 post-apply Review 当作 pre-apply 人工门禁；Apply 后评审记录可以继续存在，但不能替代 R-WB4 至 R-WB6；acceptance: 系统能分别证明“写入前已确认的冻结候选”和“写入后的可选 Review”，二者状态与证据不混用；owner/method: engineering，事务生命周期测试；provenance: 会话分析确认当前 `review_run.py` 为 post-apply 且不阻塞 Apply。
- R-WB9 — Query 应在当前多轮话题中自动发现并持续修订一个 writeback candidate draft；后续事实改变、弱化或推翻结论时，必须替换或失效旧候选，不得把多个互相矛盾的候选同时呈现为当前版本；该 draft 只存在于当前交互上下文，不创建事务或持久化普通 Query；acceptance: 多轮 fixture 中先形成初稿、再加入纠正证据后只输出修订后的当前候选，且目标仓库与 host memory 不变；owner/method: engineering，状态化会话评测与 byte-identity 测试；provenance: 用户询问多轮后如何触发 writeback，并通过 `ad-align` 接受“自动发现候选、人工触发事务”。
- R-WB10 — Query 只在候选具有复用价值且话题已基本收敛时主动提示；允许的触发信号包括用户主动询问可写回点、已有结论被纠正、知识缺口已由源码/主源关闭，或形成没有关键证据缺口的跨问题综合；普通 compiled hit、仍有关键未决证据或仅格式改写不得产生主动提示；同一话题最多提示一个当前候选；acceptance: 正向 fixtures 各产生一次简短候选提示，普通命中、未决和重复追问 fixtures 不产生噪声候选；owner/method: product + engineering，代表性问题集与候选精确率/重复率评测；provenance: 用户接受自动候选方向，同时保留对误报和打扰的约束。
- R-WB11 — 用户通过自然语言 `准备写回`、`writeback`、`先生成 staged candidate` 或等价明确意图触发 Maintainer staging；系统不得要求用户学习或调用新的 Writeback Skill。候选提示应说明该动作只生成待评审内容；真正 Apply 仍遵循 R-WB6 的后续独立确认；acceptance: Claude/Codex 代表性会话能把这些表达路由到现有 Query → Maintainer handoff，第一次触发后 live Wiki 不变且输出 review candidate，未明确触发时不创建事务；owner/method: engineering，双宿主自然语言 journey 与负向测试；provenance: 用户通过 `ad-align` 接受“复用 Query 与 Maintainer，不新增用户可见 Skill”。
- R-CS1 — AD Wiki 必须持久保存 Code Wiki/代码证据的可移植身份，至少能关联 canonical Git remote、使用过的 revision、对应 Source Summary 和 validated run；acceptance: 新会话无需读取历史聊天即可从 Wiki 元数据解析某个代码证据来源及固定 revision；owner/method: engineering，registry/run/source-summary 集成测试；provenance: 用户要求用类似 source 的持久元数据避免反复查找代码地址。
- R-CS2 — 团队可提交的代码来源身份与机器相关的本地 worktree binding 必须分离；可移植元数据不得包含用户主目录绝对路径，本地 binding 不得成为团队成员或另一台机器必须共享的事实；acceptance: portable fixture 在不同临时根目录可复用，本地映射不会进入发布的 Wiki/Skill 或泄漏主机路径；owner/method: engineering，跨根目录与打包负向测试；provenance: 当前 Code Wiki 已保存 remote/revision 但未保存本地路径，以及用户要求避免重复发现。
- R-CS3 — 当用户明确提供并成功验证一个代码 worktree 后，系统应记住该 Git 身份与本地 binding，供同一主机后续查询或 Writeback 重用；acceptance: 第二个新会话能按 canonical remote 找到已登记 worktree，无需搜索旧会话或遍历 sibling repositories；owner/method: engineering，跨进程持久化测试；provenance: 用户对重复寻找历史代码地址的直接问题。
- R-CS4 — 重用本地 worktree 前必须验证它是 Git 根目录、canonical remote 匹配、所需 revision 存在，并满足当前操作要求的 clean 状态；绑定缺失、过期、冲突或存在多个候选时必须询问用户；acceptance: 错 remote、脏 worktree、缺 revision、失效路径和多候选 fixtures 均不会被静默采用；owner/method: engineering，resolver 安全与恢复测试；provenance: 现有 Code Wiki 的代码证据边界及用户认可的安全定位约束。
- R-CS5 — Agent 不得为恢复代码仓库关联而扫描整个 workspace、按相似目录名选择替代仓库、搜索跨项目记忆作为权威或自动 clone；acceptance: 缺失 binding 时返回一个明确的代码仓库定位请求，访问证据中没有 broad directory scan、memory-derived mutation 或网络 clone；owner/method: engineering，负向行为测试；provenance: 会话复盘显示当前实现曾依赖 workspace scan，用户希望用持久元数据替代该行为。
- R-CS6 — 既有 Code Wiki run 和 Source Summary 中已经记录的 remote/revision 必须继续可用，并可作为可移植代码来源身份的迁移或重建输入；本地路径无法可靠推导时只要求用户重新绑定一次；acceptance: 旧 run fixture 升级后仍能解析 Git 身份且不伪造本地路径，完成一次显式绑定后后续会话可重用；owner/method: engineering，兼容迁移测试；provenance: sofa-wiki 当前已有多个 validated Code Wiki run，但 run 只记录 logical Git identity。

## In scope

- Query 派生 writeback candidate 的多轮识别、风险升级和授权语义；
- 当前话题内候选 draft 的自动发现、替换、收敛提示和自然语言 staging 触发；
- Maintainer 对受门禁写回的 staging、冻结、评审展示、确认失效和 Apply 行为；
- 保留单轮 low-risk 写回的低摩擦路径；
- 可移植代码来源身份、本地 worktree binding 及安全重定位；
- 既有 Code Wiki run/Source Summary 元数据的兼容读取或迁移；
- 对应的 Skill 契约、运行时、验证和用户可见说明。

## Out of scope

- 将二次确认推广到所有 Ingest、Code Wiki、Lint、Migrate 或显式非 Query 工作流；
- 新增用户可见的 `ad-wiki-writeback` Skill，或要求用户学习内部 Skill 路由；
- 在没有候选精确率证据前增加持久按钮、专用 `propose-writeback` 命令或跨会话 candidate inbox；
- 建立用户身份认证、owner allowlist、密码学签名或替代 Git/CODEOWNERS/branch protection；
- 修改 Raw `source-registry` 的不可变来源语义，或把 Git worktree 当作 Raw 文件登记；
- 自动 clone、跨组织代码搜索、全工作区扫描或远程仓库发现服务；
- 自动 commit、push、PR、merge、发布或清理既有 Wiki 工作树；
- 回写、索引或持久化普通用户 Query、完整聊天记录或跨项目 memory；
- 借本任务重构无关的 Maintainer、Code Wiki 或健康度机制。

## Constraints and confirmed decisions

- 门禁仅适用于 Query 派生的多轮综合或 medium/high-risk 语义写回。
- 多轮综合自动至少是 medium-risk；风险分类不能规避人工确认。
- Query 可以自动发现和提示 candidate，但自动化止于候选；创建 staged transaction 和 Apply 都必须由用户明确触发。
- 同一话题只保留一个当前候选，后续证据改变结论时旧候选必须失效或被替换。
- 用户通过自然语言表达 writeback 意图，不新增公开 Skill；内部继续由 Query 提议、Maintainer 执行。
- 用户查看摘要即可决定是否打开 staged diff；不要求在对话中完整展开长 diff。
- `apply` 对用户保持简单，但系统内部必须能证明它对应哪一份冻结候选；有歧义时不得写入。
- Query 保持严格只读，真正写入只能由独立 Maintainer 事务执行。
- portable code identity 与 local worktree binding 分离；不得在团队可提交或发布内容中泄漏机器绝对路径。
- 代码仓库重定位失败时优先诚实询问，不用扫描或猜测换取自动化表象。
- 当前分支、工作树、工具可用性、临时目录和本次会话路径属于 run context，不构成产品要求。

## Delegated engineering defaults and boundaries

- Engineering 可选择可逆的事务状态名、冻结摘要算法、确认关联方式和失效实现，但不得允许确认后的候选发生未重新确认的语义变化。
- Engineering 可选择 portable registry 与 local binding 的具体文件名、schema、缓存位置及相对/绝对本地路径表达；必须满足可移植性、隐私、精确匹配和可恢复性要求。
- Engineering 可选择如何从既有 validated run/Source Summary 构建初始 registry，以及 lazy migration 或显式 migration；不得删除历史证据或伪造未记录的本地路径。
- Engineering 可选择评审摘要的排版和 diff 查看方式；必须保留 R-WB5 的信息，并确保链接指向本次冻结候选。
- Engineering 可选择可逆的候选收敛启发式、提示文案和等价自然语言识别，但不得在关键证据未决时把候选表述为稳定知识，不得自动进入 staging，也不得对同一话题重复提示。
- 如果代表性评测显示自动提示噪声不可接受，产品可在后续独立决策中考虑轻量 UI action 或 `propose-writeback` 命令；该回退选项不属于当前实现范围。
- 当多个待确认候选使简单 `apply` 有歧义时，Engineering 应采用 fail-safe 行为并要求用户选定目标，不得猜测。
- 实现可分批交付 writeback gate 与 code-source resolution，但每批必须明确支持范围，不能声称未实现的另一半已经完成。

## Open product decisions

无。
