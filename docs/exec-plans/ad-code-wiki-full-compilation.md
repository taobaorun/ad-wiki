# Implementation Plan: AD-Wiki 全库自动 Code Wiki 编译

Product Contract: in-run `code-wiki-contract-2026-08-22`

Technical Design: `docs/designs/ad-code-wiki-full-compilation.md`

Requirements: R-CW1–R-CW12

Commit policy / authority: `none`；用户于 2026-08-22 授权开始本地实现，未授权 commit、push、PR 或发布。

## Implementation decisions

- 新增 canonical `ad-code-wiki` Skill；使用 Skill Creator 官方脚手架，详细页面/运行契约放在一个直接 reference，中英文实现页使用 assets 模板。
- 新增 `scripts/ad_wiki/code_wiki.py` 作为 inventory/checkpoint/finalize 深模块；CLI 薄入口位于既有 `cli.py` 与三个根脚本。
- Code repo 身份只使用固定、只读 Git 命令；一期拒绝 dirty/unborn repo，不执行代码仓库内容，也不复制整个仓库到 Raw。
- Code Wiki run 使用既有 `run.json` 顶层状态和 `staged/`，新增 `code_wiki` 子对象；Finalize 冻结 exact write set 后继续复用 `apply_run.py`。
- `operation: code-wiki` 只允许 Bundle Markdown 写入；未 finalized run 在 Apply 前被拒绝。
- 实现页使用 `wiki/implementations/<base-concept-id>.md`、`type: Concept` 与 `code-wiki` tags；代码快照 Source Summary 使用 `coverage: partial`。
- 基础 Concept 只增加 marker 管理的 implementation link；语义反馈保存在 run state 并交给后续独立 Writeback。
- Plugin minor 版本目标 `1.4.0`；OKF `0.2`、Profile `0.1`、Source Registry v1 均不迁移。

## Scope deltas

- 用户于 2026-08-22 明确授权一个 Wiki + 一个固定 SHA 本地 code repo 的窄只读双仓库输入；不扩张为通用跨仓库检索。
- 用户明确授权 Skill 自动遍历全部基础 Concept 并持久 checkpoint；不增加服务端 Batch、Connector、后台 Worker 或并发执行器。
- Product Contract 需新增 Code Wiki 例外与非目标，其他中央服务、搜索索引、远程执行和历史版本范围保持排除。

## Implementation units

### U1 — Git identity 与全 Concept inventory

- Requirements: R-CW1、R-CW2、R-CW6、R-CW9、R-CW10
- Dependencies and accepted-design pointers: Design §3、§5.1–5.2、§6、§10
- Affected modules and mutation: `scripts/ad_wiki/code_wiki.py` 新增 Git/root/inventory/run prepare；`scripts/ad_wiki/cli.py` 和 `scripts/prepare_code_wiki.py` 新增入口；`scripts/ad_wiki/core.py` 复用/最小导出 Concept helpers；`tests/test_code_wiki.py` 新增 proof-first tests。
- Entry / exit conditions: 进入时现有 Runtime 只能处理单 Wiki；退出时 clean Git revision、两个显式 root、全基础 Concept 稳定 inventory、生成物排除、潜在目标 baseline、幂等 Prepare 和 code repo byte/status 不变均由测试固定。
- Focused verification: clean/dirty/detached/unborn Git fixture；symlink/path escape；稳定排序；Source Summary/Entity/Concept 全枚举；implementations/code-wiki-source 排除；相同/冲突 run ID。
- Recovery checkpoint: 新模块和 Prepare CLI 可独立移除，不改变既有 transaction/query 行为。
- Complexity allowance: 新深模块与 run 子 Schema 由 R-CW2/R-CW10 的全库覆盖和中断恢复要求授权；不增加通用 Git provider 或跨仓库 abstraction。

### U2 — Checkpoint、Finalize 与现有 Apply 集成

- Requirements: R-CW3、R-CW7、R-CW8、R-CW9、R-CW10
- Dependencies and accepted-design pointers: U1 run identity；Design §5.3–5.4、§8–9
- Affected modules and mutation: `code_wiki.py` 增加 status/result schema、coverage、run-local lock、idempotent checkpoint、finalize；`cli.py` 与 checkpoint/finalize wrappers；`core.py/runtime.py` 增加 `code-wiki` operation、writable boundary 与 finalized Apply guard；transaction tests。
- Entry / exit conditions: 进入时 inventory 全 pending；退出时五类终态、inline result JSON、staged path contract、全部 terminal gate、code/wiki drift、exact write set freeze、未 finalized Apply 拒绝、单次原子 Apply/rollback 全部有测试。
- Focused verification: 每类 terminal status；enriched 缺 code ref/page；重复 checkpoint；retry event；run-local lock；pending finalize；extra/missing staged；dirty/HEAD drift；baseline drift；Apply success/rollback/idempotency；另一个 Wiki/code repo 字节不变。
- Recovery checkpoint: U1 Prepared runs 保持诊断可读；若 Apply integration 未收敛，可回退 `ALLOWED_OPERATIONS/WRITABLE_OPERATIONS` hunk 而不影响现有 operation。
- Complexity allowance: run-local checkpoint lock 与 finalize phase 由长任务 crash/recovery 和 existing exact-write-set gate 授权；不增加 worker、queue 或新顶层状态机。

### U3 — Code Wiki 页面契约、模板与 Skill

- Requirements: R-CW2–R-CW5、R-CW7–R-CW9、R-CW11–R-CW12
- Dependencies and accepted-design pointers: U1–U2 CLI/schema；Design §4、§6–8、§10
- Affected modules and mutation: 通过 Skill Creator 初始化 `skills/ad-code-wiki/`；编写 concise `SKILL.md`、`references/code-wiki-contract.md`、中英文 implementation templates、`agents/openai.yaml`；Runtime 增加 template/static checks 与 managed link validation；Query contract 补充 base→Companion 导航；packaging/content tests。
- Entry / exit conditions: 进入时无第三 Skill/页面约定；退出时双宿主发现同一 Skill，完整自动遍历流程、真实 snippet/provenance、Mermaid 条件、测试未执行披露、差异分类、secret guard、managed link 与反馈边界均由 Skill/reference/template 和静态测试固定。
- Focused verification: Skill quick validator；frontmatter description trigger；openai.yaml；模板版本/语言；Companion 必需 heading/source/link/snippet；marker idempotency/conflict；禁止绝对路径、伪代码冒充、敏感内容和语义自动修复。
- Recovery checkpoint: Skill/模板/packaging 是独立层，可在 Runtime 保留内部测试接口时整体撤回。
- Complexity allowance: 独立 Skill 和一个直接 reference 由后置独立生命周期、双宿主单实现及 Skill context budget 授权；不创建 README/安装指南/额外 prompts。

### U4 — Product/发行契约与端到端 fixture

- Requirements: R-CW1–R-CW12
- Dependencies and accepted-design pointers: U1–U3 完整行为；Design §11–14
- Affected modules and mutation: canonical Product Contract/team workflow/model-navigation docs；双 Manifest、Runtime version、所有 generated template provenance 和 packaging tests 升至 `1.4.0`；新增小型 Wiki + Git code fixture 的 CLI/behavior acceptance。
- Entry / exit conditions: 进入时实现未反映到产品/发行身份；退出时窄双仓库和全库 workflow 被正式记录，旧 Wiki 无迁移，完整 fixture 自动评估所有基础 Concept、生成至少一个 Companion/managed link/source summary、保留 docs-only/no-code-match、输出 feedback/coverage，并能分别回答文档与源码问题。
- Focused verification: `prepare → checkpoint(all) → finalize → apply → lint → query probes`；Plugin doctor；双 Manifest；Plugin/Skill validators；旧 minimal Wiki 和所有既有测试回归。
- Recovery checkpoint: 版本/文档最后切换；若行为验收失败，保持 `1.3.0` 身份并返回相应 Runtime/Skill 单元修复。
- Complexity allowance: none；只同步已实现的公开行为和现有版本落点。

## Verification contract

- Required baseline: 在首个 mutation 前记录 `python3 -m unittest discover -s tests`、Plugin/Skill validators 和 `git diff --check` 当前结果。
- Required focused: 每个单元列出的 unit/CLI/transaction/packaging tests。
- Required full: `python3 -m unittest discover -s tests -v`、`python3 -m compileall -q scripts tests`、`git diff --check`、Codex Plugin validator、三个 Skill quick validators、`claude plugin validate . --strict`。
- Required isolation: Code Wiki 前后 code repo HEAD/index/worktree bytes 不变；另一个 Wiki 全文件摘要不变；失败/未 finalize run 不改变 live Bundle。
- Required behavioral: fixture 中每个基础 Concept 都有终态；coverage 算术一致；文档问题命中基础页，源码问题命中 Companion；部分结果不得报告完整。
- Preferred experiential: 在用户完成的 SOFA Wiki 与最新 SOFA code repo 上运行真实 `ad-code-wiki`，审阅 Mermaid、核心代码、全库 coverage、差异反馈和源码问答。
- Fallback experiential: 若真实 SOFA code repo 尚未提供或宿主认证不可用，以本地 Git fixture + 一个可用宿主的前向运行替代；明确损失真实规模、领域匹配和跨宿主体验，不能据此发布 `1.4.0`。
- Experiential owner: 用户；缺失真实 SOFA 验收不阻止本地实现完成，但阻止版本发布结论。

## Risks and recovery

- 自动匹配可能产生错误实现页：完整 Concept + implementation/caller/test 交叉证据；不确定进入 `needs-review`，fixture 与 SOFA dogfood 检查。
- 全库长任务可能中断：稳定 inventory、单页 checkpoint、resume pending、一次 final Apply；run state 是恢复点。
- Wiki/code 长运行漂移：Prepare/Checkpoint/Finalize 固定 code SHA/clean，Finalize/Apply 固定 Wiki baseline；漂移新建 run，不自动重基线。
- 页面/代码体积膨胀：Companion 分层和核心 snippet contract；不复制全文件/全 repo。
- 敏感代码泄漏：显式 code root、危险路径/secret guard、代码不执行、疑似内容转 `needs-review`。
- 新 code-wiki run schema 出现实现复杂度：保持一个 `code_wiki.py` 深模块、复用现有 run/apply，不引入通用 job framework。

Recovery：所有 live Wiki 写入继续由现有 snapshot rollback 负责；实现期间无 commit policy，Git worktree 和测试提供恢复边界；Code repo 始终只读。

## Definition of done

- `ad-code-wiki` 自动评估全部基础 Concept，不接受用户 selector。
- 每个 inventory Concept 有合法终态，coverage 与 residuals 诚实。
- enriched 页面具备文档契约、实现原理、必要 Mermaid、真实核心代码、符号、测试阅读声明、差异和 revision provenance。
- 基础 Wiki 构建/Query 不依赖 Code Wiki；Code Wiki 失败不改变 live Bundle。
- code repo 固定 SHA、clean、只读且不执行。
- staged checkpoint 可恢复，Finalize 冻结 exact write set，既有 Apply 原子写入并可回滚。
- 语义 Wiki 问题只输出 feedback/Writeback candidates，不在 Code Wiki run 中静默修复。
- 双宿主发现第三 Skill，唯一 Runtime，Plugin `1.4.0` 身份一致，OKF/Profile 不变。
- 全量工程验证通过；真实 SOFA 验收若缺失被明确记录为发布前 residual。
