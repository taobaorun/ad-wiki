# Implementation Plan: AD-Wiki Codex / Claude Code 双宿主兼容

Product Contract: `docs/product-specs/ad-wiki-repository-local-scope.md`

Technical Design: `docs/designs/ad-wiki-codex-claude-plugin-compatibility.md`

Requirements: R1-R8, R10-R14

Commit policy / authority: `delivery-only`; 用户先通过 `ad-lfg` 授权本地实施、验证和审查，后于 2026-08-16 明确授权 commit、push 和创建 PR

## Implementation decisions

- 发布 Plugin `0.3.0`，保持 OKF `0.2`、AD-Wiki Profile `0.1` 和既有 run schema 不变。
- 新增 Claude Code 原生 Manifest 与 Marketplace；保留 Codex 原生文件。仓库根就是唯一 Plugin 根，两个 Catalog 共同以 `./` 指向它。
- 根级 `skills/` 是 canonical、可扩展的 Skill 集合；当前只包含 `ad-wiki-maintainer`，后续新增 Skill 不需要改变发行层级。
- 只维护一个 `ad-wiki-maintainer/SKILL.md`、一组 references/assets 和一套 Python Runtime；宿主差异仅进入 Manifest、Catalog 与 Skill root 解析说明。
- 正式发行要求两个 Manifest 版本完全一致且无 build metadata。Codex 开发 cachebuster 不属于本计划的正式发行物。
- 不安装到开发者现有宿主配置。安装级验证优先使用隔离配置目录或临时用户；若某宿主不能安全隔离，则官方 validator 与无持久化 discovery smoke 为该环境的上限，并如实记录缺失证据。

## Scope deltas

- 相对 `0.2.0` 仅增加 Claude Code 打包入口、共享 Skill 的安装后路径解析规则、版本同步和双宿主测试。
- 不增加新的 Wiki 操作、远程依赖、MCP、App、Hook、Agent、身份系统、批量导入或 Attested Runtime。
- 既有但与本任务无关的 `.agents/skills/`、`.claude/`、规模化平台设计和其他工作树改动不属于本计划的实现范围。

## Implementation units

### U1 — 建立双宿主原生打包契约

- Requirements: R1, R4-R8, R10, R13-R14
- Dependencies and accepted-design pointers: Technical Design sections 3-5, 8-9
- Affected modules and mutation: 根级 `.claude-plugin/marketplace.json`、`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、Runtime `PLUGIN_VERSION`、模板与版本说明
- Entry / exit conditions: 进入时仅 Codex 可原生安装；退出时两个 Catalog 指向同一 Plugin 根、两个 Manifest 都是 `ad-wiki` `0.3.0`，且均不声明延期能力
- Focused verification: JSON parse、Manifest contract tests、Codex validator、Claude strict validators
- Recovery checkpoint: 新增 Claude Adapter 可以独立移除；Wiki/Profile 无迁移

### U2 — 让 canonical Skill 在两个安装位置可靠调用 shared Runtime

- Requirements: R2-R4, R11-R12, R14
- Dependencies and accepted-design pointers: Technical Design sections 6-7
- Affected modules and mutation: `skills/ad-wiki-maintainer/SKILL.md`、workflow reference、packaging tests
- Entry / exit conditions: 进入时命令示例可能被误解为相对知识仓库 cwd；退出时 Skill 明确从宿主提供的 Skill 位置解析 Plugin root，校验闭包后调用唯一 Runtime
- Focused verification: Skill validation、静态路径契约测试、临时 Plugin copy 中的命令执行、Claude cache 布局等价测试
- Recovery checkpoint: 路径说明变更不触碰 Runtime 数据或知识仓库格式

### U3 — 证明双端发现、版本一致和仓库行为一致

- Requirements: R1-R8, R10-R14
- Dependencies and accepted-design pointers: U1-U2、Technical Design section 10
- Affected modules and mutation: `tests/test_packaging.py`，必要的测试 fixture 或无持久化验证脚本
- Entry / exit conditions: 进入时只有 Codex packaging assertion；退出时自动化能阻断 Manifest/Catalog 漂移、重复核心、延期能力声明和缓存路径错误
- Focused verification: 完整 unittest、compileall、Codex/Claude 官方 validators、隔离安装与 list/details、两个临时知识仓库的 Init/Query/受门禁写入一致性
- Recovery checkpoint: 所有测试知识库和宿主配置位于临时目录，失败后不改变开发者全局配置

### U4 — 更新面向团队的安装与兼容文档

- Requirements: R10-R14
- Dependencies and accepted-design pointers: U1-U3、Technical Design sections 5 and 8
- Affected modules and mutation: canonical team workflow design中的发行结构、Manifest、安装和验证章节，以及必要的 Skill reference
- Entry / exit conditions: 进入时文档只描述 Codex；退出时团队能区分两端安装命令、Claude namespace、共同核心和无 Wiki 迁移升级语义
- Focused verification: 文档路径/命令与最终 Manifest 对照、链接检查、`git diff --check`
- Recovery checkpoint: 文档更新与运行时代码分离，可独立校正

## Verification contract

- Baseline evidence, required: 以 HEAD `e3eebaa` 加本计划明确拥有的工作树路径为 basis；排除 `.agents/skills/`、`.claude/`、`docs/designs/ad-wiki-scale-platform.md` 以及本任务开始前的其他无关改动。
- Focused evidence, required: packaging tests、两个官方 Plugin validator、官方 Skill validator、版本与 capability assertions。
- Cross-unit evidence, required: `python3 -m unittest discover -s tests -v`、`python3 -m compileall -q scripts tests`、临时复制后的 Runtime help/init/validate。
- Installation evidence, required for complete dual-host claim: Codex 与 Claude Code 均在隔离宿主配置中 add Marketplace、install Plugin 并观察 list/details；不允许以开发者全局配置完成测试。
- Behavior evidence, required: 两端加载同一 Skill，确定性 Runtime 的目录结构、JSON schema、Raw hash、validation codes 和事务状态一致；自然语言逐字一致不属于要求。
- Experiential acceptance, preferred: 真实团队成员分别完成一次 Codex 和 Claude Code 安装及调用。Owner: 团队用户；pending-human 不阻止本地工程完成，但阻止宣称真实团队体验已接受。
- Fallback evidence: 若宿主 CLI 缺失，不接受 fallback；该宿主兼容结论必须报告为未验证。若 CLI 存在但模型调用需要外部认证，允许 validator + isolated install/list/details 代替 Agent 自然语言前向测试，损失仅限真实模型调用体验，authority 来自本计划。

## Risks and recovery

- 两套 Manifest 元数据漂移：由 packaging test 比较稳定身份和正式版本。
- Claude Plugin cache 改变文件绝对路径：所有 Runtime 必须位于 Plugin 根内，Skill 从自身位置解析，不使用发行仓库相邻路径。
- 宿主 CLI 验证可能写入用户配置：只在官方隔离配置或临时用户/容器中运行；无法证明隔离时停止该命令而不是污染现有环境。
- 文档当前存在本任务之前的工作树改动：只修改双宿主相关段落，审查时单独列出本任务拥有的 hunk。

## Definition of done

- Codex 与 Claude Code 的原生 Manifest 和 Marketplace 都通过各自官方校验并解析到同一 Plugin 根。
- 正式 Plugin 身份在两端均为 `ad-wiki` `0.3.0`，Runtime 与模板记录一致。
- 根级 `skills/` 可以继续新增 Skill；当前 Maintainer Skill、其 references/assets 和 Runtime 都只有一份 canonical 实现。
- Skill 在仓库 checkout 和 Claude cache 等价布局中都能定位、调用 shared Runtime，不依赖知识仓库 cwd。
- 两端不声明 MCP、App、Hook、Agent 或任何被延期的中央能力。
- 完整测试、编译、打包、隔离安装和行为一致性证据通过；人工体验状态单独报告。
- 本地实现经过最终验证与代码审查；未获得发布授权时停在 `local-complete`。
