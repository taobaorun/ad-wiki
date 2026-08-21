# Technical Design: AD-Wiki 模型直读导航 v1.2

Design identity: `ad-wiki-model-navigation-v1.2-accepted`

Product Contract: `docs/product-specs/ad-wiki-repository-local-scope.md` R15-R28

Authority: 用户于 2026-08-20 明确要求完全删除 `build_query_context`，不保留兼容；千页以内信任模型通过 Wiki 与本地文本搜索自主检索，超过约 1000 页后再基于证据考虑 BM25；于 2026-08-21 要求 Wiki 可被不具备脚本执行能力的 Agent 使用。

## 决策摘要

- Query 与 Maintainer 直接读取 `ad-wiki.yaml`、Bundle 索引和完整 Markdown 页面。
- 模型使用任意可用的文件读取或仓库搜索能力在明确 Bundle 内导航，可迭代关键词、同义词、标识符和链接；Shell、脚本和 `rg` 只是可选增强。
- Init 生成 canonical `AGENTS.md` 静态 Query 契约和只导入它的 `CLAUDE.md` 薄适配，使未安装 Plugin 的 Agent 也能识别并查询 Wiki。
- 删除 `search_wiki.py`、`build_query_context.py`、builtin scorer、Discovery/Hydration/Context Envelope、search 配置和公开 Runtime API；不保留 Query API 兼容入口。
- 保留 `query_registered_raw.py`，仅用于模型已读相关 Concept 后的一次窄范围 cache miss。它继续通过 Concept provenance、注册表、路径和哈希限制 Raw。
- 新事务从 `PLANNED` 直接 Apply；`approve_run.py` 仅作为一版无写入兼容 shim，旧已批准事务仍验证既有 staged hash。
- Source Summary 用 `coverage: full | partial` 表达阅读覆盖；partial 是 reviewable compilation debt，不能报告完整导入。
- 内部关系统一使用标准 Markdown Bundle 链接，Validator 报告 `[[wikilinks]]`。

## 责任边界

```text
Model / Skill
  ├─ understand the question or source
  ├─ navigate indexes and Markdown links
  ├─ search Bundle text and refine terms
  ├─ choose full pages to read
  ├─ synthesize, cite, and expose gaps
  └─ inspect staged semantic diffs

Deterministic Runtime
  ├─ resolve one explicit repository
  ├─ register and guard immutable Raw
  ├─ constrain optional Raw fallback
  ├─ validate OKF, coverage, and links
  └─ enforce staged writes, baseline, lock, rollback, indexes, and logs
```

Runtime 不再拥有“哪些 Wiki 页面相关”的判断权。搜索命中只是模型的导航线索；事实依据来自模型实际读取的页面。

静态 Agent 入口不加载知识正文、不执行代码，也不复制完整 Skill。它只声明仓库身份、索引优先导航、引用、只读与知识缺口规则；具体检索仍由 Agent 的可用文件能力完成。

## Query 数据流

```text
question
  → host loads AGENTS.md directly or through a thin adapter
  → read ad-wiki.yaml and wiki/index.md
  → follow relevant directory indexes
  → navigate/search within bundle_root using available file capabilities
  → read full relevant Concepts
  → refine search or follow Markdown links when needed
  → optional registered-Raw fallback for one narrow missing detail when command execution exists
  → cited read-only answer
```

不存在固定 Top-K、候选分数阈值、Hydration selection 数量或 pre-model 字符预算。查询不得扫描其他仓库，也不得写 Wiki、Raw、运行状态、host memory 或全局配置。

## Maintainer 数据流

```text
registered source / writeback request
  → navigate current Wiki directly
  → read complete impact set and source
  → prepare exact read/write sets
  → stage compiled knowledge
  → inspect complete semantic diff
  → direct apply with transaction protections
  → validate, probe representative questions, report coverage and residuals
```

`domain` 描述长期 Wiki；当前导入范围不改写该身份。Source Summary 的 `coverage: full` 只在完整阅读来源后使用。可复用知识不能永久停留在 Raw 或 catch-all Summary。

## 兼容与迁移

- 删除的 Query CLI、Python exports 和 Context schemas 没有兼容期；调用者必须改用模型直接导航。
- 旧知识仓库中的 `review`、`search` mapping 可被 Runtime 忽略读取，不需要 Profile migration，也不会出现在新 Init 配置中。
- 旧 `APPROVED`/`AUTO_APPROVED` 事务可继续 Apply，并保持其 staged hash 绑定。
- OKF 保持 `0.2`，AD-Wiki Profile 保持 `0.1`。旧仓库缺少静态 Agent 入口时 Validator 给出 warning；使用原 domain/language 显式重跑 Init 可补齐缺失文件，非一致既有文件绝不覆盖。

## 延期能力

BM25、中文 bigram、长度归一化、向量检索、重排和 Search MCP 均不属于 v1.2。Wiki 超过约 1000 页只是重新评估 BM25 的触发条件；是否建设必须由真实查询召回、成本和延迟证据决定。

## 验证

- 静态：删除的脚本、Runtime exports、Skill 引用和 search 配置不存在。
- Runtime：Raw fallback、直接 Apply、旧事务、路径隔离、回滚、coverage 与链接校验通过。
- Packaging：两个 Manifest 同为 `1.2.0`，Plugin doctor 和模板检查通过。
- 行为：有 Plugin Agent 与只有项目说明/文件读取能力的无脚本 Agent，都能通过 index + Bundle Markdown 回答代表性问题；Query 字节只读；Maintainer 检查 staged diff，不写运行时 host memory，不把 partial 报告成完成。
