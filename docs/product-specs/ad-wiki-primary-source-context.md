# Product Contract: AD Wiki Primary-Source-Aware Context

Authority: 用户于 2026-08-22 确认 Agent 在 compiled Wiki 信息不足时无需询问用户，应自动读取精确登记的本地 Raw，并在本地证据不足或时效性关键时读取精确上游主源；用户不需要理解或选择 Wiki 内部证据路径；用户随后明确要求把已讨论的 Wiki 健康指标补充为产品规约。

Product Context: not-available；本合同是独立的新任务权威，不修改既有 Product Contract 的历史要求。

## Actor and observable outcome

使用 AD Wiki 的团队成员直接提出领域问题，无需理解 Wiki、Raw、Source Registry、Code Wiki 或 fallback。Agent 自动选择最小充分证据路径，从持久编译知识下降到精确 Primary Sources，并返回有来源、快照边界和不确定性说明的答案。

## Requirements

- R-PSC1 — Raw、源码和 commit 是 Primary Sources；Wiki 是持久编译、导航、综合和路径压缩层，不替代主源；acceptance: Query/Code Wiki 契约和代表性回答能区分 compiled Wiki、local Raw、code revision 与 upstream source；owner/method: engineering，静态契约与行为回放；provenance: Karpathy LLM Wiki Architecture、DeepWiki Primary Sources/Path Compression 实践及用户确认。
- R-PSC2 — Agent 必须自动执行渐进式证据路径 `Index/ToC → 完整相关 Concept → provenance-bound Primary Source descent`，不得要求用户选择是否查询 Wiki、Raw 或主源；acceptance: 用户只问领域问题即可得到答案或诚实缺口，过程中无证据模式确认问题；owner/method: engineering，Claude/Codex 前向会话；provenance: 用户明确“不需要询问，用户也不理解你的 wiki”。
- R-PSC3 — 普通 compiled hit 不读取 Raw；只有已读相关 Concept 缺少窄事实、步骤或验证证据时才下降；acceptance: compiled-hit 仓库字节不变且无 Raw/外部访问，cache-miss 能绑定已读 Concept；owner/method: engineering，Query journey 与访问证据；provenance: Karpathy Query/index-first 模式与 AD Wiki 既有 cache-miss 边界。
- R-PSC4 — Plugin Runtime 是本地 Raw fallback 的首选增强，不是资格门槛；Runtime 不可用或片段不足时，有文件读取/搜索能力的 Agent 可通过 Source Registry 将已读 Concept 的精确 `canonical_locator` 解析到最新登记记录，只读一个相关文档或章节；acceptance: 有脚本和无脚本 Agent 都能完成同一代表性窄查询，无脚本路径不扫描 Raw 目录、不读取无关 registry entry、不声称 Runtime hash verification；owner/method: engineering，双能力前向测试；provenance: 用户对无脚本 Agent 的既有要求及本轮确认。
- R-PSC5 — 本地登记证据缺失、不足或时效性关键时，Agent 自动读取 Concept 声明的精确上游 Primary Source，无需再次询问；acceptance: 只访问相关 locator/文档，回答标注其位于 compiled snapshot 之外及可见更新时间，不静默混合快照；owner/method: engineering，受控外部源 fixture/前向测试；provenance: 用户本轮明确授权自动证据下降、DeepWiki Agent Search/MCP context 实践。
- R-PSC6 — 有界的含义是 provenance、来源、文档/章节和资源预算受限，不是禁止读取 Primary Sources；acceptance: 负向测试拒绝全 Raw 目录扫描、无 Concept 来源扩张、无关外部搜索和跨 Wiki 读取；owner/method: engineering，安全与边界测试；provenance: 用户对绝对禁止 Raw 的质疑及 Primary Sources 原则。
- R-PSC7 — Context Poisoning 防护优先于覆盖数量；不确定、冲突、过期、歧义或无法定位的证据不得被平滑成确定知识；acceptance: evidence state、冲突、缺口和 freshness 边界在影响结论时显式呈现，错误信息不自动写入 Wiki；owner/method: engineering，负向 fixtures 与回答评测；provenance: DeepWiki Context Poisoning 原则。
- R-PSC8 — Primary Source descent 可自动产生 concise writeback candidate，但 Query 保持只读；只有用户明确授权的独立 Maintainer 操作才能修改 Wiki；acceptance: Query 不写 Bundle、Raw、log、host memory 或外部系统，候选可被后续维护消费；owner/method: engineering，byte identity 与 workflow test；provenance: Karpathy“good answers can be filed back”及 AD Wiki 团队治理边界。
- R-PSC9 — 基础 Wiki 构建必须把 ToC、关键系统和 canonical terminology 作为结构质量对象；acceptance: 完整构建能说明主要系统边界、页面结构与 Glossary 覆盖，不能只按文件目录机械生成页面；owner/method: product/engineering，真实仓库结构评测与用户验收；provenance: DeepWiki ToC/Glossary 实践。
- R-PSC10 — Code Wiki 继续自动评估全部已有基础 Concept；目录、Symbol Graph、Git 活跃度和可用运行时信号只能决定执行顺序、调查深度和 unknown-unknown 候选，不能静默遗漏低分 Concept；acceptance: `evaluated == inventory_total`，每个 Concept 有明确终态，Agent 可在异常时扩展或重新判断候选；owner/method: engineering，coverage/incremental/agentic journey；provenance: 用户此前明确全 Concept 自动执行及 DeepWiki Agentic Core 实践。
- R-PSC11 — Wiki 健康度必须使用下述 `R-HM*` 指标向量判断，不得用页面数量或一个可抵消硬错误的综合分数代替；acceptance: 健康报告完整覆盖适用指标、硬门禁和不可用原因，且每项能追溯到确定性证据或显式评测；owner/method: engineering/product，指标契约测试与真实用户验收；provenance: DeepWiki quality metrics/Unknown Unknowns 实践及用户明确要求补充产品规约。
- R-PSC12 — 初始化示例与正式文档的 source locator、Raw bytes、source ID、coverage 和引用必须一致；部分摘录或转述不得冒充完整主源；acceptance: 最小示例使用可访问的正确 locator，登记哈希匹配，partial/full 声明与实际读取范围一致；owner/method: engineering，packaging/provenance validation；provenance: 重读 Karpathy Gist 时发现当前最小示例使用不同且不可匿名读取的 Gist ID、Raw 仅为三行转述。

## Wiki health metrics

- R-HM1 — 健康报告是指标向量而不是单一总分；每项必须输出 `metric_id`、`value`、`numerator`、`denominator`、`scope`、`evidence`、`calculated_at`、`status: pass | warning | fail | unavailable` 和 `unavailable_reason`；acceptance: schema validation 拒绝缺失分母/证据的比率和无原因的 `unavailable`，报告不生成 overall score；owner/method: engineering，schema/property tests；provenance: 用户确认的指标定义及 Context Poisoning 原则。
- R-HM2 — Correctness Gates 必须独立判定且不可由其他指标抵消：Source Integrity = 100%、Citation Validity = 100%、Broken Managed Links = 0、未披露 Snapshot Inconsistency = 0、Code Wiki Concept Evaluation = 100%、Invalid Code References = 0、Silent Detected Conflicts = 0；acceptance: 任一 gate 失败时报告整体状态不得为 healthy，并提供失败对象列表和证据；owner/method: engineering，deterministic validation/negative fixtures；provenance: Primary Sources、全 Concept 覆盖与 Context Poisoning 要求。
- R-HM3 — Key System Coverage 定义为 `被 ToC/Concept 实质表达的关键系统 / 已识别关键系统`；“实质表达”要求具备入口、责任边界、核心机制、依赖方向和 Primary Source，分母必须来自可审查且绑定 revision 的 key-system inventory；acceptance: 报告展示逐系统 coverage evidence，只有标题或目录占位不得计入分子；owner/method: product/engineering，inventory review 与真实仓库评测；provenance: DeepWiki ToC 是首要质量对象的实践。
- R-HM4 — ToC Completeness 必须分别报告关键系统的入口、边界、机制、依赖、来源和跨页链接完整度，不得以页面数代替；acceptance: 每个维度有分子分母和缺失系统列表，目录结构变化后能检测 drift；owner/method: engineering/product，结构 validation 与用户审阅；provenance: DeepWiki ToC/关键系统实践。
- R-HM5 — Glossary Coverage 定义为 `已定义并统一使用的 canonical terms / 已检测 canonical terms`，并覆盖同义词、缩写、历史名称、文档—代码名称差异和版本重命名；acceptance: denominator、term evidence 和未定义/冲突词列表可审查，无法稳定识别术语时返回 `unavailable`；owner/method: engineering/product，术语 fixtures 与领域评审；provenance: DeepWiki canonical terminology/Glossary 实践。
- R-HM6 — Active Code Coverage 定义为 `被 Concept 或 Companion 引用/绑定的活跃代码权重 / 候选活跃代码总权重`；候选只使用可用的 Git 活跃度、Symbol Graph、公共入口和运行时信号，排除 generated/vendor/fixture 等明确非目标；acceptance: 每个权重和排除原因可追溯，缺少相应信号时按维度降级或返回 `unavailable`，不得声称所有文件覆盖；owner/method: engineering，Git/graph fixtures 与真实代码库回放；provenance: DeepWiki active-file coverage 和多信号 codebase graph 实践。
- R-HM7 — Evidence Health 必须报告 Primary-Source Coverage、Citation Depth、Conflict Visibility 和 Ambiguity Visibility；Citation Depth 区分仅指向知识库/仓库入口与定位到文档章节、commit、path、symbol/source location 的深引用；acceptance: 每项有 material-claim 或 citation 分母，未标注的冲突/歧义进入 correctness finding，不得按普通缺失平滑处理；owner/method: engineering，claim/citation fixtures 与语义评测；provenance: Primary Sources、引用深度和 Context Poisoning 实践。
- R-HM8 — Freshness and Maintenance 必须报告 Source/Code Snapshot Freshness、Stale Rate、Orphan Rate、Source-to-Concept Yield 和索引 drift；acceptance: stale/orphan/yield 均给出分子分母与对象列表，代码绑定能说明目标 revision，Source Summary coverage 不能代替 answer-bearing Concept yield；owner/method: engineering，clock/revision/index fixtures；provenance: Karpathy Lint、persistent compounding 与 DeepWiki freshness 要求。
- R-HM9 — Unknown Unknowns 只能通过代理信号呈现，不得宣称已测量全部未知知识；代理至少包括高中心度未绑定 symbol、高频修改但无 Companion 的文件、未进入 Glossary 的高频术语、Source Summary 已覆盖但无 answer-bearing Concept 的主题、代表性问题无法回答的区域；acceptance: 报告名称明确为 risk signals，列出证据对象和趋势，不生成“unknown unknown coverage”；owner/method: engineering/product，graph/source/eval-set analysis；provenance: DeepWiki Unknown Unknowns 原则。
- R-HM10 — Representative Question Success 必须基于版本化、人工可审查的代表性评测集，把结果分类为 compiled hit 成功、Primary Source descent 成功、诚实 knowledge gap、错误答案和错误导航；acceptance: 每次评测绑定 Wiki/source/code revision，展示分类计数和失败样例，不从普通用户 Query 日志构造评测集；owner/method: product/engineering，离线行为评测；provenance: DeepWiki“最终指标是用户价值”及 AD Wiki 不记录 Query 的边界。
- R-HM11 — Evidence Descent Success 定义为 `需要下降时成功定位正确 Primary Source 的问题 / 需要下降 Primary Source 的代表性问题`；acceptance: 评测同时验证 Agent 未向用户询问 Wiki/Raw/MCP 模式、未访问无关来源并正确披露 snapshot boundary；owner/method: engineering，Claude/Codex 双宿主 journey；provenance: 用户明确自动下降且无需询问。
- R-HM12 — Path Compression Gain 必须把 Wiki-assisted journey 与 raw-only/code-only 基线比较，至少报告到达正确证据所需步骤、读取文件数、输入 token、首次正确答案时间和错误导航次数；acceptance: 比较使用相同问题、模型/能力、来源 revision 和预算，缺少可比基线时返回 `unavailable`；owner/method: engineering/product，受控 A/B 行为评测；provenance: DeepWiki Path Compression 与 Karpathy compiled-once 原则。
- R-HM13 — Wiki/Repository Scale Relationship 用于发现大仓 Wiki 被固定上限截断，不作为单仓库页面数目标；acceptance: 只有存在可比仓库 cohort 或同一仓库可比增长序列时才报告相关性/增长曲线，否则返回 `unavailable`，不得集中上传私有仓库统计；owner/method: product/engineering，本地或显式授权的离线 cohort analysis；provenance: DeepWiki wiki-size/repository-size quality metric 与 AD Wiki 无中央遥测边界。
- R-HM14 — User Usefulness 只能来自显式任务验收、离线评测或自愿反馈，至少区分是否解决问题、是否可执行、是否帮助理解原理、是否成功定位源码和是否仍需询问维护者；acceptance: 普通 Query 不被持久化、不创建 host memory，报告列明反馈样本和采集方式；owner/method: product，用户验收/自愿反馈；provenance: DeepWiki 用户价值原则及 AD Wiki 隐私边界。
- R-HM15 — 除 R-HM2 的 correctness gates 外，首版覆盖率和价值指标不得设置无证据的统一通过阈值；acceptance: 指标先报告 baseline、趋势和对象级缺口，只有经真实仓库与用户验收校准后才能在独立产品决策中升级为 gate；owner/method: product，阈值 provenance review；provenance: 指标分母差异、信号可用性约束和避免虚假健康结论的原则。

## In scope

- Query Skill 触发可见性和静态 Agent 契约；
- compiled-first、自动 provenance-bound local Raw 与精确 upstream descent；
- 有 Runtime/无 Runtime 的可移植 Query 行为；
- Primary Source、compiled snapshot、freshness 和 uncertainty 披露；
- Query-to-writeback candidate 的只读交接；
- 基础 Wiki 的 ToC、关键系统和 Glossary 质量目标；
- Code Wiki 全 Concept 覆盖下的信号辅助排序、调查深度与 unknown-unknown 发现；
- 可验证且诚实降级的 Wiki 健康指标；
- 统一健康指标输出字段、不可抵消的 correctness gates、对象级证据和 `unavailable` 语义；
- 示例来源与 coverage 修复。

## Out of scope

- 复制 DeepWiki 的集中式服务、百万仓库基础设施或组织级跨仓库索引；
- Graphify runtime、artifact 或 schema 依赖；
- 将 Runtime、Shell、CLI、MCP 或脚本设为 compiled Query 前提；
- 固定 Top-K、预先字符预算或确定性 scorer 替代模型阅读 Wiki；
- 因评分低而省略任何已有 Concept；
- 自动修改 Wiki、自动合并、自动发布或把 Query 写入日志；
- 无 provenance 的全 Raw 搜索、无关外部搜索或跨 Wiki 检索；
- 把 Wiki 页面、Source Summary 或 Code Wiki Companion 声称为 Primary Source；
- 用单一综合分数、页面数量或无分母百分比宣称 Wiki 健康；
- 未经用户授权集中采集仓库统计、普通 Query 或隐式使用反馈。

## Constraints and confirmed decisions

- 用户只表达领域意图，不承担 AD Wiki 内部路由和证据模式选择。
- Agent 对只读证据下降拥有默认权限；写回、外部写入、代码执行、commit、push、PR 和发布仍需各自授权。
- 本地登记快照优先于实时上游；上游用于本地证据缺失、不足或时效性关键的情况，并必须披露差异。
- Code Wiki 的全 Concept 自动评估要求保持不变；重要性信号不能成为遗漏授权。
- Query 不创建 host memory，不记录用户问题，不自动维护 Wiki。
- 健康报告不记录普通 Query；用户价值使用版本化离线评测集、显式任务验收或自愿反馈。
- Correctness gates 使用固定零容忍/完整通过语义；其他指标在没有真实校准证据前只作为 baseline、趋势和缺口诊断。
- Raw 与外部内容始终作为不可信证据数据，不作为 Agent 指令。
- 当前工作分支、worktree、已写代码、工具可用性和临时测试环境属于 run context，不构成产品要求。

## Delegated engineering defaults and boundaries

- Engineering 可选择可逆的文档边界识别、关键词扩展、资源预算、信号权重、指标文件格式和缓存布局，但不得改变自动下降、全 Concept 覆盖、Primary Source 层级或只读边界。
- Engineering 可在 `.ad-wiki/` 保存可删除重建的导航/指标状态；不得把模型查询、用户问题或外部凭据持久化。
- Engineering 可选择指标计算的可逆数据结构、可视化和权重公式，但必须公开 numerator、denominator、scope、evidence、排除项和信号可用性；不得生成一个可掩盖 correctness gate 的总分。
- 无法证明来源、完整性、时效性或指标分母时，默认报告 unknown/unavailable，不得猜测。
- ToC、Glossary、signal ranking 和质量指标可以分迭代交付，但每次发布必须明确实际覆盖，不得用未来能力包装当前结果。

## Open product decisions

无。
