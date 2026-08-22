# Technical Design: AD-Wiki 全库自动 Code Wiki 编译

Design identity: `ad-code-wiki-full-compilation-v0.1-accepted`

Product Contract: in-run `code-wiki-contract-2026-08-22`

Requirements covered: R-CW1–R-CW12

Authority: 用户于 2026-08-22 确认 Code Wiki 与基础 Wiki 构建解耦；基础 Wiki 完成后再提供最新代码仓库；Code Wiki 必须自动遍历全部 Concept，而不是由用户选择局部页面；代码用于补充实现原理、核心源码、测试和 Mermaid 图，文档仍代表对外契约；Wiki 问题需要反馈，语义修复不得静默发生。

Design status: accepted；用户于 2026-08-22 以“开始实现”明确接受本设计并授权本地实现。

## 1. Current behavior, constraints, and invariants

当前 Plugin `1.3.0` 只有 `ad-wiki-query` 与 `ad-wiki-maintainer` 两个根级 Skill：

- Query 只读导航一个显式 AD Wiki，不写 Bundle 或运行状态。
- Maintainer 维护一个显式 AD Wiki，通过 `prepare_run.py → staged/ → apply_run.py` 完成 baseline-bound、可回滚写入。
- `register_source.py` 只登记 Wiki `raw_root` 内的单个不可变文件；Source Registry v1 不支持目录或外部 Git 仓库。
- `prepare_run.py` 要求在规划时给出非空、精确的 `write_set`；`apply_run.py` 拒绝缺失或额外 staged 文件。
- Runtime 没有“遍历全部 Concept、逐项 checkpoint、恢复长任务”的运行协议。
- OKF Bundle 中所有非 reserved Markdown 页面都可作为 Concept；现有索引构建器会递归处理新目录，因此 Code Wiki 页面不需要改变 OKF `0.2`。
- 当前 AD-Wiki Profile `0.1` 允许 `type: Concept` 和未知 Frontmatter 字段；Code Wiki 不需要新增持久 Schema 类型。
- 模型拥有语义判断和页面综合；确定性 Runtime 只拥有边界、身份、完整性、状态、事务和验证。

必须保留：

1. 基础 Wiki 在没有代码仓库、没有 Code Wiki Skill 时完全可用。
2. Markdown/OKF Bundle 与 Git 仍是知识真源。
3. 文档说明是对外契约；代码是固定 revision 的当前实现证据，不能单独证明设计意图。
4. Code Wiki 不直接编辑 live Bundle；所有写入必须经过 staged diff、baseline、lock、validation 和 rollback。
5. 代码、注释、测试和 README 都是不可信证据数据，不具有 Agent 指令权。
6. Code Wiki 构建可以要求维护 Agent 具备文件和命令能力；这不改变普通 Query 的零脚本最低能力基线。

## 2. Confirmed product requirements

- **R-CW1 — 独立生命周期**：基础 Wiki 先独立构建和使用；Code Wiki 是后置、可选的第二次编译。验收：未运行 Code Wiki 的仓库继续通过现有 Query/Lint，且 Plugin 升级不自动启动 Code Wiki。
- **R-CW2 — 全库自动覆盖**：用户只提供 Wiki 根与最新代码仓库；Skill 自动枚举并评估全部原始 Concept。验收：coverage 中 `evaluated == inventory_total` 才可结束全库评估。
- **R-CW3 — 每页终态**：每个 Concept 必须得到 `enriched | docs-only | no-code-match | needs-review | failed` 之一。验收：不存在静默遗漏或仍为 `pending` 的页面。
- **R-CW4 — Code Wiki 内容**：`enriched` 页面必须包含基础 Concept 链接、当前实现原理、必要 Mermaid 图、真实核心代码、关键符号、相关测试、文档—代码关系、revision 与来源。验收：模板和行为测试覆盖全部必需部分。
- **R-CW5 — 文档优先边界**：对外用法和公共契约默认沿用文档；代码补充当前实现。验收：差异被标为实现补充、待确认差异或已确认差异，不把一次代码阅读表述成“纠正文档”。
- **R-CW6 — 最新快照**：一期只支持一个最新 Git 代码仓库 revision，不承担历史版本比较。验收：每个实现页绑定同一个 commit SHA，Prepare、Checkpoint 或 Finalize 发现 HEAD/工作区变化时停止；Apply 只消费已冻结 staged bytes，不重新依赖 code worktree。
- **R-CW7 — 反馈与修复分离**：Code Wiki 自动收集 Wiki 缺口、粒度、别名、断链、差异和错误候选。验收：语义反馈默认只报告；只有独立授权的标准 Writeback 才修复基础知识。
- **R-CW8 — 完整性诚实**：全部页面被评估不等于全部源码知识完成。验收：存在 `needs-review`、`failed` 或代码相关的 `no-code-match` 时，结果标为 partial，并列出 residuals。
- **R-CW9 — 代码仓库只读**：Skill 不修改或执行目标代码。验收：只接受 clean Git worktree，结束时 HEAD/status 不变；不运行构建、测试或仓库内脚本。
- **R-CW10 — 故障隔离与恢复**：分析失败或中断不改变 live Wiki；运行可按 Concept checkpoint 后恢复。验收：中断前结果保留在 `.ad-wiki/runs/<run-id>/`，未 finalize 的 run 不能 Apply。
- **R-CW11 — 完整流程验证**：Code Wiki 运行必须覆盖 Query 现有 Wiki、编译实现页、反馈、Lint 和代表性 Query acceptance。验收：文档问题与源码问题分别命中基础 Concept 和实现 Companion。
- **R-CW12 — 双宿主单实现**：Codex 与 Claude Code 发现同一个 canonical Code Wiki Skill，共享同一 Runtime 和内容契约。验收：无两套 Prompt/Runtime，双宿主 packaging validator 通过。

## 3. Decision summary and active design dimensions

1. 新增独立根级 Skill `ad-code-wiki`，不扩充 Maintainer 的公开路由。它与 Query/Maintainer 不建立 Skill-to-Skill 运行依赖，只共享确定性 Runtime。
2. 一次运行显式绑定两个本地根：一个可写 AD Wiki 和一个只读、clean、固定 HEAD 的 Git 代码仓库。这是用户授权的窄范围双仓库工作流，不开放通用跨 Wiki 检索或 Batch API。
3. Runtime 在开始时生成全部 Concept 的稳定 inventory 与 baseline；模型逐项语义评估，Runtime 原子 checkpoint 结果。用户不选择 Concept。
4. 实现知识写入独立 Companion 页面 `wiki/implementations/<base-concept-id>.md`；页面仍使用 `type: Concept`，无需 Profile migration。
5. `enriched` 的基础 Concept 获得一个 Runtime 管理的最小实现链接块，不改写原有事实正文；实现页反向链接基础 Concept。
6. 一个 Code Wiki run 先把全部输出保存在既有 run 的 `staged/`；全部 Concept 进入终态后才 freeze 精确 `write_set`，随后复用现有 `apply_run.py` 原子 Apply/rollback/index/log/validation。
7. 代码来源以 Git commit SHA 提供不可变身份，不复制整个代码仓库到 Wiki Raw；生成一个代码快照 Source Summary，并在实现页中记录 repo locator、revision、文件路径、符号和测试。
8. 语义 Wiki 修复不混入 Code Wiki Apply；运行只应用 Companion、代码来源摘要和可识别的基础页链接块。其余反馈输出为独立 Writeback candidates。
9. 这是向后兼容的 Plugin minor 功能；实现目标版本为 `1.4.0`，OKF 保持 `0.2`，AD-Wiki Profile 保持 `0.1`。

本次必须设计清楚的方面包括：新 Skill/Runtime 责任边界、双仓库输入协议、长任务 checkpoint、exact-write-set 冻结、Code Wiki 页面约定、代码证据的 trust/provenance、失败恢复和兼容行为。

## 4. Proposed structure and responsibilities

```text
skills/ad-code-wiki/
├── SKILL.md                         # 全库编译编排和语义判断
├── agents/openai.yaml               # 双宿主同一 Skill 入口
├── references/code-wiki-contract.md # 页面、分类、反馈和完成契约
└── assets/templates/
    ├── implementation.md
    └── zh-CN/implementation.md

scripts/
├── prepare_code_wiki.py             # 固定两个仓库身份并生成全 Concept inventory
├── checkpoint_code_wiki.py          # 原子记录单 Concept 结果并校验 staged 输出
└── finalize_code_wiki.py            # 要求全终态并冻结 exact write_set

scripts/ad_wiki/
├── cli.py                            # 三个 CLI 入口
├── code_wiki.py                      # inventory/checkpoint/finalize 深模块
├── core.py                           # 复用 Concept/路径/哈希基础能力
└── runtime.py                        # 复用 apply/rollback/index/log；识别 code-wiki operation

wiki repository during a run
.ad-wiki/runs/<run-id>/
├── run.json                          # canonical run identity/state/coverage
└── staged/                           # 尚未进入 live Bundle 的完整输出
    └── wiki/...
```

### Responsibility boundary

**`ad-code-wiki` Skill owns**：

- 读取全部 inventory Concept；
- 判断代码相关性和终态；
- 在显式 code root 内查找模块、符号、调用链和测试；
- 综合实现原理、Mermaid、源码片段、差异与反馈；
- 写入 run-scoped staged Markdown；
- 检查 staged semantic diff；
- finalize 后调用既有 Apply；
- 运行 Lint 和代表性 Query acceptance；
- 返回全库 coverage、feedback 和 residuals。

**Deterministic Code Wiki Runtime owns**：

- 校验 Wiki root、code root、Git HEAD、clean status、路径和 symlink 边界；
- 枚举完整 Concept inventory，排除 reserved/index/log 与既有 `wiki/implementations/` 输出；
- 捕获 Wiki Concept baseline、潜在 Companion 目标 baseline、代码 revision 和运行身份；
- 原子 checkpoint 每个 Concept 的 status/output/code refs/feedback；
- 保证每个 inventory 项恰有一个终态；
- 校验 enriched staged 页面结构、目标路径和托管链接块；
- freeze exact read/write set；
- 在 Prepare、Checkpoint 和 Finalize 确认 Wiki baseline 与代码 HEAD/status 未漂移；
- 把 frozen run 交给现有 `apply_run.py`。

**Existing transaction Runtime owns**：

- repository lock；
- exact staged bytes；
- baseline drift；
- live writes；
- indexes/log；
- Bundle/Raw validation；
- rollback；
- final `VALIDATED` state。

## 5. Public interfaces

### 5.1 Skill entry

```text
$ad-code-wiki --wiki-repo <wiki-root> --code-repo <git-root> [--run-id <id>]
```

- `wiki-repo` 必须是已初始化且验证通过的 AD Wiki。
- `code-repo` 必须是本地 Git worktree，HEAD 已提交且工作区/索引 clean。
- `run-id` 省略时由宿主生成稳定、合法的运行 ID；恢复时必须显式使用原 ID。
- 不接受 Concept selector、path filter、Top-K、score threshold 或历史 revision 参数。

### 5.2 Prepare

```bash
python3 <plugin-root>/scripts/prepare_code_wiki.py \
  --repo <wiki-root> \
  --code-repo <git-root> \
  --run-id <run-id> \
  --json
```

成功结果至少包含：

```json
{
  "run_id": "code-wiki-sofa",
  "operation": "code-wiki",
  "status": "PLANNED",
  "wiki": {"root": "<not persisted as an answer>", "bundle": "wiki"},
  "code_source": {
    "revision": "<40-char-sha>",
    "remote": "<normalized-url-or-null>",
    "worktree_clean": true
  },
  "coverage": {
    "inventory_total": 42,
    "evaluated": 0,
    "pending": 42
  },
  "concepts": [
    {
      "concept_id": "concepts/extension-point",
      "path": "wiki/concepts/extension-point.md",
      "baseline_sha256": "...",
      "status": "pending"
    }
  ],
  "staging_root": ".ad-wiki/runs/code-wiki-sofa/staged"
}
```

绝对路径只用于本地命令结果，不得写入最终 Wiki 页面或面向用户的可移植答案。

### 5.3 Checkpoint

```bash
python3 <plugin-root>/scripts/checkpoint_code_wiki.py \
  --repo <wiki-root> \
  --code-repo <git-root> \
  --run-id <run-id> \
  --concept <concept-id> \
  --status <enriched|docs-only|no-code-match|needs-review|failed> \
  --result-json '<json-object>' \
  --json
```

`--result-json` 的稳定字段：

```json
{
  "reason": "human-readable bounded rationale",
  "implementation_path": "wiki/implementations/concepts/extension-point.md",
  "code_refs": [
    {
      "path": "src/.../ComponentManagerImpl.java",
      "symbol": "ComponentManagerImpl#registerExtension",
      "kind": "implementation"
    },
    {
      "path": "src/test/.../ComponentManagerImplTest.java",
      "symbol": "shouldRegisterPendingExtension",
      "kind": "test"
    }
  ],
  "feedback": [
    {
      "kind": "apparent-divergence",
      "summary": "文档描述 A；当前代码观察到 B；需要确认版本/部署边界"
    }
  ]
}
```

`--result-json` 接收 JSON object 字符串，不读取任意外部结果文件。较长的 Markdown 正文仍由 Skill 写入受 run root 约束的 staged 路径。

规则：

- `enriched` 必须提供合法 `implementation_path`、至少一个 implementation code ref，以及对应 staged Companion。
- `docs-only` 必须说明为何该 Concept 没有有价值的实现层。
- `no-code-match` 表示 Concept 与实现相关但没有可靠匹配，不等于 docs-only。
- `needs-review` 表示多个候选或文档—代码边界无法可靠判断。
- `failed` 只记录真实处理失败；不得用它跳过难页。
- checkpoint 对同一 Concept/同一内容幂等；不同结果必须显式重试并留下替换事件。

### 5.4 Finalize and Apply

```bash
python3 <plugin-root>/scripts/finalize_code_wiki.py \
  --repo <wiki-root> --code-repo <git-root> --run-id <run-id> --json

python3 <plugin-root>/scripts/apply_run.py \
  --repo <wiki-root> --run-id <run-id> --json
```

Finalize 必须：

1. 拒绝任一 `pending` Concept；
2. 再次验证 code HEAD、clean status 和 Wiki baseline；
3. 验证 staged 文件恰好对应 enriched pages、一个 code snapshot Source Summary，以及 Runtime 管理的基础页 link blocks；
4. 冻结 `read_set`、`write_set`、staged hashes 与 coverage；
5. 标记 `code_wiki.finalized: true`；
6. 保持 run `status: PLANNED`，让既有 Apply 状态机继续拥有 live write transition。

`apply_run.py` 对 `operation: code-wiki` 使用与 writeback 相同的 Bundle-only写入规则。未 finalized 的 Code Wiki run 必须拒绝 Apply。

## 6. Inventory and automatic classification

### Inventory boundary

Prepare 稳定枚举 Bundle 内所有非 reserved、非 Code Wiki 生成物的 Markdown Concept，包括 Source Summary、Entity、Concept、Synthesis、Open Question 和领域扩展；排除：

- 任意 `index.md`；
- Bundle-root `log.md`；
- hidden/reserved paths；
- `wiki/implementations/**`；
- 带 `code-wiki-source` tag 的代码快照 Source Summary，避免下一次运行递归处理生成物。

Inventory 按 repository-relative path 排序。运行开始后 inventory 不增长；Wiki 发生变化即视为 baseline drift，必须重新准备运行。

### Model-owned classification

Skill 必须读取每个 Concept 的完整正文，再在 code root 内逐步查找同义词、公开类型、配置键、模块、符号、测试和调用方。名字相似只能产生候选，不能决定终态。

默认判断：

- 行为机制、生命周期、扩展点、配置解析、类加载、调用链、并发、缓存、容错、诊断等进入 `enriched` 或明确 residual 状态。
- 纯发布公告、人员流程、外部链接目录、没有实现语义的来源页通常为 `docs-only`。
- 找不到可靠代码但主题显然涉及实现时使用 `no-code-match`，不得强行生成低质量页面。

Runtime 不实现关键词评分器、向量检索、Top-K 或自动相关性阈值。

## 7. Code evidence and page contract

### Code source identity

- 一期只支持 Git worktree；untracked/modified/staged changes、unborn HEAD 或不存在 commit 时拒绝 Prepare。Detached HEAD 只要指向有效 commit 且 worktree clean 即可接受。
- revision 使用完整 commit SHA；远端 URL 存在时规范化后记录，缺失时使用 `urn:git-snapshot:<sha>` 并披露不可远程解析。
- 运行期间不 checkout、fetch、pull、build、test 或执行 code repo 内容。
- 代码页引用 `revision + relative path + symbol`；行号只是辅助，不能作为唯一身份。
- 一个 run 生成一个带 `code-wiki-source` tag 的 Source Summary：`wiki/sources/code-<repo-slug>-<shortsha>.md`。由于 Skill 只读取与 Wiki Concept 相关的代码范围，该页必须使用 `coverage: partial` 并列出实际读取/未读取边界，不能声称覆盖整个仓库。

### Companion path

基础 Concept ID 映射为：

```text
wiki/<family>/<path>.md
  → wiki/implementations/<family>/<path>.md
```

例如：

```text
wiki/concepts/extension-point.md
  → wiki/implementations/concepts/extension-point.md

wiki/entities/sofa4.md
  → wiki/implementations/entities/sofa4.md
```

Companion 使用现有 `type: Concept`，并带 `tags: [code-wiki, implementation]`。这保持 OKF/Profile 兼容，同时让索引自动发现新目录。

### Managed base link

Runtime 只管理以下边界块，不改写基础页其他正文：

```markdown
<!-- ad-code-wiki:start -->
## 实现原理

- [查看源码实现](/implementations/concepts/extension-point.md)
<!-- ad-code-wiki:end -->
```

- `content_language: en` 使用 `## Implementation` 与 `View source implementation`。
- 已有一致 managed block 时幂等替换。
- 存在重复/损坏 marker，或页面有未托管但语义冲突的实现链接时，Concept 进入 `needs-review`，不得猜测合并。
- 该链接块属于 Code Wiki enrichment，不属于对基础文档事实的“纠正”。

### Required Companion body

每个 enriched Companion 必须依次包含：

1. 基础 Concept 与代码快照范围；
2. 文档公开契约摘要；
3. 当前实现原理与关键不变量；
4. 运行流程图：当机制包含三个以上状态/步骤/参与者时必须使用 Mermaid，否则说明无需图；
5. 真实核心代码片段，每段标注 revision/path/symbol，省略部分必须显式标记；
6. 关键类、方法、配置和调用关系；
7. 相关测试源码所声明的边界，并明确这些测试在本流程中只被阅读、没有执行；
8. 文档与代码关系：一致、实现补充、待确认差异或已确认差异；
9. 不确定性、未读取范围和继续阅读入口；
10. claim-level source footnotes。

禁止：

- 大段复制整个文件；
- 伪造不存在的类、方法、测试或 Mermaid 关系；
- 从代码形状推断未经证据支持的设计动机；
- 把内部实现描述成稳定公共 API；
- 把模型改写的伪代码冒充真实源码；
- 嵌入凭据、私钥、token、`.env` 或其他敏感内容。

## 8. Feedback and repair boundary

每个 Concept 可以产生以下 feedback kind：

- `knowledge-gap`；
- `granularity`；
- `alias`；
- `broken-link`；
- `implementation-only`；
- `apparent-divergence`；
- `confirmed-divergence`；
- `suspected-wiki-error`。

Code Wiki run 会持久化 feedback 到 run.json 并在最终报告去重汇总，但不会把 feedback 自动写成 Bundle 页面。

同一 Code Wiki Apply 允许的基础页变化只有 managed implementation link。语义修复必须满足：

1. 用户任务另外明确包含 Wiki 修复授权；
2. Code Wiki run 先结束并给出 feedback；
3. Maintainer 重新导航相关页面和证据；
4. 通过独立 `operation: writeback` 的 prepare/stage/diff/apply；
5. 文档—代码冲突默认保留双重陈述，不静默覆盖对外文档知识。

这保证 Code Wiki 可以发现和推动修复，但不会用自动源码匹配扩大语义写权限。

## 9. State, idempotency, failure, and recovery

### Run state

Code Wiki 复用现有顶层状态：

```text
DISCOVERED → PREFLIGHTED → PLANNED
                         → APPLIED → VALIDATED
任意 Apply 失败 → FAILED + rollback
```

全库编译进度保存在 `run.json.code_wiki`，不新增第二套顶层状态机：

```json
{
  "schema_version": "1",
  "finalized": false,
  "code_source": {"revision": "...", "remote": "..."},
  "concepts": [{"concept_id": "...", "status": "pending"}],
  "coverage": {
    "inventory_total": 42,
    "evaluated": 0,
    "enriched": 0,
    "docs_only": 0,
    "no_code_match": 0,
    "needs_review": 0,
    "failed": 0,
    "pending": 42,
    "quality": "partial"
  }
}
```

`quality`：

- `complete`：无 pending/needs-review/failed，且没有代码相关的 no-code-match；
- `partial`：全部已评估但存在上述 residual；
- 运行中始终是 `partial`，不得宣称完整。

### Idempotency and resume

- 相同 run ID + 相同 Wiki baseline + 相同 code SHA 的 Prepare/Checkpoint/Finalize 幂等。
- 恢复时 Skill 读取 run.json，只处理 `pending` 或用户明确要求 retry 的 terminal failure。
- 同一 run 同时只允许一个 writer；checkpoint 使用 run-local O_EXCL lock 和 atomic JSON replace。
- code HEAD/status 在 Prepare、Checkpoint 或 Finalize 漂移，或任一 inventory/base target baseline 在 Finalize/Apply 漂移时停止，保留 run 作为诊断证据；重新 Prepare 新 run，不自动重基线。
- Apply 前 live Wiki 未变化；中断或分析失败只留下 `.ad-wiki/runs` state/staged drafts，不改变 Bundle。
- Apply 失败复用现有 snapshot rollback，恢复所有 Bundle/index/log 字节。

### Final result

最终返回：

- code repo revision；
- inventory/evaluated 和五类终态计数；
- created/updated Companion；
- managed links；
- deduplicated feedback；
- representative Query results；
- `complete | partial` quality；
- exact residual Concept IDs 和恢复方式。

## 10. Security, trust, and resource boundaries

- 两个 repo root 都必须显式传入并独立解析；不得从父目录、用户主目录或相似仓库猜测。
- Wiki 是唯一可写根；code repo 全程只读，Skill 不执行其构建、测试、hooks、scripts、Makefile 或嵌入指令。
- 禁止读取 `.git` 对象内容以外的敏感配置、`.env`、凭据文件、私钥、构建产物、vendored/binary 大文件；Git identity 查询只使用固定只读命令。
- 所有 symlink 必须解析在所属 root 内；越界立即失败。
- 代码片段进入 Wiki 前必须检查明显 secret/private-key/token 模式；疑似敏感内容不复制并将 Concept 标为 `needs-review`。
- 一个 run 只支持一个 code repo 和一个 Wiki；不引入远程 Connector、网络爬取、中央 Worker、跨 Wiki 查询或后台任务。
- 不新增用户身份、ACL 或审批系统；真实读写权限仍由本地文件系统和 Git 托管平台负责。

## 11. Compatibility and migration

- Code Wiki 是显式调用的可选能力；安装 `1.4.0` 不自动扫描已有 Wiki 或代码仓库。
- 现有 Wiki 没有 `wiki/implementations/` 时无需迁移；首次成功 Apply 懒创建目录和索引。
- Companion 仍是标准 OKF Concept；旧 Query/Maintainer 可以读取和索引它们，即使不理解 code_wiki run metadata。
- AD-Wiki Profile 保持 `0.1`，OKF 保持 `0.2`；`.ad-wiki/runs` 新字段是 Plugin 运行状态，不改变 Bundle interchange contract。
- Plugin downgrade 不删除 Companion 或 managed links；旧版本会把它们视为普通 Markdown。未完成 Code Wiki run 可由旧版本忽略，但不能继续。
- 当前 Product Contract 的“禁止通用跨仓库检索/Batch”继续有效；本设计只增加一个用户显式提供、固定 SHA、只读代码证据仓库的窄工作流。

## 12. Alternatives and rejected approaches

### A. 首次 Wiki Ingest 同时强制扫描代码

拒绝。它破坏基础 Wiki 的独立可用性，增加首次交付时间，并使没有代码访问权的 Wiki 无法构建。

### B. 用户逐页选择 Concept

拒绝。用户明确要求 Skill 自动处理全部 Concept，并输出可证明的全库 coverage。

### C. 每个 Concept 都强行生成实现页

拒绝。它会把文档型、公告型和无实现语义页面转成低质量 Code Wiki；“跑全部”定义为全部评估，而不是全部生成。

### D. 直接把实现内容追加到原 Concept

拒绝。文档契约与实现知识生命周期不同，混写使页面过长、差异难表达、Code Wiki 失败影响基础知识。Companion + managed link 保持可选分层阅读。

### E. 把整个代码仓库复制到 Raw

拒绝。体积、敏感信息、重复存储和刷新成本过高。clean Git SHA 已提供不可变身份，核心代码片段进入可移植 Companion。

### F. 不持久化 inventory/checkpoint，只靠一个 Agent 会话跑完

拒绝。全库任务可能跨 context compaction 或会话中断，无法证明全部 Concept 被评估，也无法安全恢复。

### G. 每页处理后立即 Apply

拒绝。一半完成的 Code Wiki 会进入 live Bundle、产生大量日志和中间索引状态。run-scoped staged checkpoint + 一次原子 Apply 保留故障隔离。

### H. Code Wiki 自动修复所有发现的 Wiki 问题

拒绝。代码不自动推翻对外文档，且源码匹配不能扩大语义写权限。反馈和标准 Writeback 分离。

## 13. Risks and verification approach

### Risk: 自动代码匹配错误

控制：读取完整 Concept；使用代码、调用方和测试交叉验证；名字匹配只作候选；不确定进入 `needs-review`；行为回放检查典型页面。

### Risk: 全库运行成本和中断

控制：稳定 inventory、单 Concept checkpoint、只处理 pending 的恢复、无 live writes、最终 coverage；不增加中心调度器或并发 worker。

### Risk: 长运行期间 Wiki/code 漂移

控制：Prepare 捕获全部基线和 code SHA/clean status；Checkpoint/Finalize 重验 code repo，Finalize/Apply 重验 Wiki baseline；漂移时新建 run，不自动合并不确定结果。

### Risk: 页面膨胀和代码复制

控制：Companion 分层、只取证明机制的核心片段、完整文件通过 revision/path/symbol 定位、源码页可进一步拆分但不复制整个仓库。

### Risk: 文档被实现细节污染

控制：基础页只添加 managed link；对外契约留在基础页；实现页明确 internal/current revision；语义反馈单独 Writeback。

### Required engineering evidence

- Runtime unit：完整 inventory、排除生成页、稳定排序、Git clean/SHA、路径与 symlink、checkpoint schema/幂等、coverage 计数、pending finalize 拒绝、drift、exact staged set、未 finalized Apply 拒绝、rollback。
- CLI integration：prepare → 多状态 checkpoint → finalize → apply → validate；中断后 resume；相同 run 幂等；另一个 Wiki 和 code repo 字节不变。
- Content contract：中英文 Companion 模板、managed link、Mermaid 条件、真实 snippet provenance、测试引用、差异/不确定性、secret guard。
- Packaging：第三个 canonical Skill 被双宿主发现；唯一 Runtime；Manifest 版本、模板 provenance 与 Plugin `1.4.0` 一致；Plugin/Skill validators 通过。
- Behavioral acceptance：小型 fixture 全 Concept 自动评估；文档型问题命中基础 Concept，源码型问题命中 Companion；no-code-match/needs-review/failed 诚实披露。
- Experiential acceptance：在完成的 SOFA Wiki 和用户提供的最新 SOFA code repo 上跑完整流程，用户审阅 coverage、至少一个 Mermaid/核心代码页面、差异反馈和源码类问答。该体验证据是发布 `1.4.0` 前的必需人工验收。

### Preferred and fallback evidence

- Preferred：真实 Claude Code 与 Codex 前向运行均完成同一 fixture 和 SOFA 试点。
- Fallback：某宿主认证/工具不可用时，可用另一宿主真实运行 + canonical Skill 静态 validator；必须披露缺失的跨宿主体验证据，不能把 fixture unit tests 冒充模型语义质量。

## 14. Scope deltas and specialist evidence

相对当前 `docs/product-specs/ad-wiki-repository-local-scope.md`，本设计包含两个已获用户授权的范围增量：

1. 新增一个本地、显式、只读 code repo 输入，作为 Code Wiki 证据源；它不是通用跨仓库搜索。
2. 新增一个全 Concept 自动批处理 workflow 与持久 checkpoint；它不是服务端 Batch、Connector、后台 Worker 或中央队列。

Implementation 必须更新 canonical Product Contract 以表达这两个窄例外，并保持原有更广非目标不变。

不需要 Security、Migration 或独立 Document Review specialist：没有远程执行、凭据、数据迁移或破坏性 cutover。实现后的 code trust/path/secret 边界必须在普通代码审查中重点检查。

## 15. Decision coverage and simplicity check

- 新 Skill：由独立后置生命周期和不扩充 Maintainer 路由的要求驱动。
- 双 repo：由用户提供独立最新代码仓库且基础 Wiki 已存在驱动；限制为一个显式只读 Git repo，拒绝通用化。
- 全 inventory/checkpoint：由“Skill 自动跑全部”和长任务中断风险驱动；无状态单会话无法证明覆盖。
- Companion + managed link：由文档/实现生命周期解耦和联合阅读体验驱动；直接混写更简单但破坏已确认边界。
- Git SHA 而非 Raw 全量复制：由不可变 provenance、体积和敏感信息风险驱动。
- 一次 Apply：由基础 Wiki 故障隔离驱动；逐页 Apply 更易实现恢复但会泄漏部分 live 状态。
- Feedback/Writeback 分离：由文档对外权威和不得静默纠正驱动。
- 不引入并发 worker、中央服务、搜索索引、新 Profile 类型、历史版本或代码执行，避免超出当前需求。

两个实现者在模块边界、输入协议、状态/恢复、页面路径、链接约定、证据身份、写入时机、修复边界和兼容策略上不再需要自行发明产品语义；剩余文件内 helper、CLI 参数解析细节和测试 fixture 组织属于可逆实现选择。

## 16. Open technical decisions

无。
