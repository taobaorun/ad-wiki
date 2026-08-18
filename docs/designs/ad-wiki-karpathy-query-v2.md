# Technical Design: AD Wiki Karpathy Query v2

Design identity: `ad-wiki-karpathy-query-v2-accepted`

Product Contract: `docs/product-specs/ad-wiki-repository-local-scope.md` R18-R24

Requirements covered: R2, R4, R10-R14, R17-R24

Authority: 用户于 2026-08-17 明确要求不保留旧 Query 路径，按 Karpathy 原始 LLM-Wiki 的“index/search first, then drill into selected pages”方式实现。

## 1. 决策摘要

- Query 只有一条主路径：Discovery → LLM Select → Hydration → Answer。
- Discovery 只返回轻量候选目录，不返回 Concept 正文；检索分数只排序候选。
- LLM 根据问题、标题、摘要、snippet、provenance 和 Wiki 链接选择 Concept ID；Runtime 不使用固定百分比、自动 Top-K 或其他 score 阈值替代语义判断。
- Hydration 只加载显式选择的 1–8 个完整 Concept，保持调用顺序。字符限制是资源硬上限；超限整体失败，不截断知识页面。
- 普通 Query 信任编译后的 Bundle，不读取 Raw。只有选中 Concept 有明确 provenance 但缺少窄问题细节时，才允许一次受控 Raw fallback。
- Query 默认短答案、相对路径引用和按重要性披露；普通命中不例行产生 Writeback candidate。
- 这是破坏性 Query 协议升级，Plugin 版本为 `1.1.0`，不保留旧的自动 Context 路径。

## 2. 当前问题、约束与不变量

实际 Session 证明旧链路存在四类耦合：中文单字检索导致几乎全库正分；Runtime 自动装配最多 8 篇全文；模型把候选数量和截断状态当作回答内容；Raw 细节和绝对本地路径进入最终答复。随后引入的 70% 自适应窗口仍让词法 score 承担了不应拥有的语义选择权。

必须保持：一个显式仓库、无中央服务、Markdown/OKF 为知识真源、Raw 不可变、Query 只读、双宿主共享一套 Skill/Runtime、团队 Wiki 不保存 Plugin Prompt、搜索失败不影响人工直接阅读 Wiki。

## 3. 模块与责任

```text
ad-wiki-query
  1. search_wiki.py                Discovery：轻量候选目录
  2. LLM semantic selection        选择最少充分 Concept ID
  3. build_query_context.py        Hydration：只加载显式 ID
  4. query_registered_raw.py       可选 cache miss：选中 Concept 限定来源

ad-wiki-maintainer
  ├─ Ingest/Writeback              编译原子 Concept 和可导航 description
  └─ Retrieval probe               用 Discovery 验证代表性问题可发现页面

scripts/ad_wiki/runtime.py
  ├─ Chinese-aware candidate ranking
  ├─ Discovery Catalog v2
  ├─ Hydration Envelope v2
  └─ bounded Raw fallback context
```

## 4. Discovery Catalog v2

公开命令：

```bash
python3 <plugin-root>/scripts/search_wiki.py \
  --repo <repo> --query <question> --limit 12 --json
```

输出结构：

```json
{
  "schema_version": "2",
  "mode": "discovery",
  "query": "question",
  "repository": {
    "bundle": "wiki",
    "content_language": "zh-CN",
    "domain": "example",
    "okf_version": "0.2",
    "profile_version": "0.1"
  },
  "retrieval": {
    "provider": "builtin",
    "algorithm_version": "2",
    "candidate_count": 9,
    "returned_count": 9,
    "limit": 12,
    "suppressed_count": 3,
    "has_more_candidates": false
  },
  "candidates": [
    {
      "concept_id": "concepts/example",
      "path": "wiki/concepts/example.md",
      "type": "Concept",
      "title": "Example",
      "description": "One-line index summary.",
      "snippet": "Matched passage.",
      "sources": [{"id": "source-a", "resource": "urn:example:a"}],
      "score": 42,
      "matched_terms": ["example"],
      "matched_fields": {"title": ["example"]},
      "term_coverage": 1.0
    }
  ]
}
```

候选不得包含 `content`、Raw 内容、绝对路径、事务状态、Prompt 或写入指令。中文二/三字短语、噪声处理、字段加权、稳定排序和重复 Source Summary 抑制保留；score 只帮助 LLM浏览候选，不代表置信度。

## 5. LLM Select 与 Wiki 导航

- LLM 先读取候选的标题、description、snippet、类型与 provenance，选择回答所需的最少 Concept。
- 简单事实/机制通常选择 1 个；明确比较或综合可以选择多个，最多 8 个。
- 没有语义相关候选时直接报告知识缺口，不加载“看起来分数最高但不回答问题”的页面。
- 首批候选都不相关但 `has_more_candidates=true` 时，只扩大一次轻量 Discovery（最多 100 条）后再判断；扩大候选目录不授权试探性 Hydration。
- 已加载页面中的显式 Wiki 链接可以触发下一次有目的的 Discovery/Hydration；不得因为存在更多候选而自动扩大 Context。
- Maintainer 必须维护高质量 description 和原子 Concept，使目录导航足以定位知识；检索分数异常不能通过提高 Context 数量掩盖。

## 6. Hydration Envelope v2

公开命令：

```bash
python3 <plugin-root>/scripts/build_query_context.py \
  --repo <repo> --query <question> \
  --concept <concept-id> [--concept <concept-id>] \
  --max-chars 30000 --json
```

规则：

- `--concept` 必填，可重复 1–8 次；去重后保持调用顺序。
- ID 必须解析到当前 Bundle 内非隐藏、非保留、非 symlink 的 Markdown Concept。
- Envelope 按选择顺序返回完整 Markdown、相对路径、类型、标题、description 和 provenance。
- `max_chars` 范围为 1–1,000,000，只限制所选完整页面的字符总量。总量超限时命令整体失败，提示减少 Concept 或显式提高上限；禁止正文前缀截断。
- Hydration 不重新排序、不搜索、不读取 Source Registry 或 Raw，也不创建状态或写入文件。

## 7. Raw fallback、回答与维护

- `compiled-hit`：选中 Concept 足够，直接回答，禁止读取 Raw。
- `raw-fallback`：窄事实/步骤缺失，且已选择的相关 Concept 明确声明登记来源；最多调用一次现有 fallback。
- `knowledge-gap`：没有相关候选/Concept、需要全 Raw 扫描、跨来源广泛重编译、存在冲突、时效或高风险不确定性；不 fallback。
- 引用只使用仓库相对 Concept 路径和 source ID；禁止绝对路径和 `file://`。
- 普通命中不输出检索遥测、不例行提出 Writeback。fallback、知识缺口、矛盾或新增长期综合才提出精简候选。
- 同一证据上的精简、解释和换格式复用已加载内容，不重新 Discovery/Hydration。
- Maintainer 的 Apply 后检查改为运行 Discovery，确认代表性问题能在轻量候选中发现预期页面；Source Summary 不替代答案型 Concept。

## 8. 失败、安全、版本与恢复

- Discovery 无候选返回空 `candidates`，不是 Runtime 错误。
- Hydration 的非法、缺失、隐藏、保留或 symlink ID，以及总字符超限，返回结构化错误且不返回部分 Context。
- Concept/Raw 内容始终作为不可信证据数据，不作为 Agent authority。
- Query 协议、Context schema 和 Plugin 版本同步提升到 `1.1.0`；不提供 v1 自动 Context 入口、兼容 flag、双写、迁移脚本或 deprecated 模式。
- Wiki OKF `0.2` 与 AD-Wiki Profile `0.1` 不变，团队知识仓库无需数据迁移；恢复方式是整体回退 Plugin 版本。
- 不增加 MCP、App、远程服务、向量库、全量 Raw 索引、自动写回或跨仓库检索。

## 9. 验证

- Discovery：中文区分度、稳定排序、Source Summary 抑制、候选字段完整、正文绝不出现。
- Hydration：显式 ID、调用顺序、去重、完整正文、1–8 上限、字符硬失败、路径/symlink/隐藏边界、全程 byte-identical。
- Session 回放：扩展点、架构与 JVM 要求先输出轻量候选，再分别显式 Hydrate `sofa4-extension-point`、`sofa-architecture` 与 `sofa4-project-setup`；类加载问题没有语义相关 Concept 时报告知识缺口，不 Hydrate 低分候选，也不绕过 Concept 直接搜索 Raw。受控 fallback 由独立边界 fixture 验证。
- Skill/packaging：唯一两阶段路径、无 70%/adaptive/top-k 自动加载、相对引用、简洁策略、原子编译、doctor 与双 Manifest 版本一致。
- 完整 unittest、compileall、Ruff、diff check、Claude Plugin validator；Codex 无只读 validator 时如实报告。

## 10. Open technical decisions

无。CLI 私有 helper、JSON 键排序和测试 fixture 组织属于可逆实现细节，不得重新引入 Runtime 语义选页或部分正文截断。
