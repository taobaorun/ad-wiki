# Implementation Plan: AD Wiki Karpathy Query v2

Product Contract: `docs/product-specs/ad-wiki-repository-local-scope.md` R18-R24

Technical Design: `docs/designs/ad-wiki-karpathy-query-v2.md`

Requirements: R18-R24

Commit policy / authority: none；用户授权本地实现，未授权 commit、push 或 PR。

## Implementation decisions

- 将现有未发布的 Query Quality 分支直接修订为破坏性的 `1.1.0`，不保留 v1 自动 Context API、兼容 flag 或迁移代码。
- 保留 dependency-free、repository-local Python Runtime；Discovery 复用中文 Search v2 排序，Hydration 使用显式 Concept ID。
- 字符限制在读取所有选中页面后原子判断，超限失败而不截断正文。
- 真实 Session 仅作为只读回放证据，不复制 sofa4 内容进发行仓库。

## Scope deltas

- 删除 70% adaptive selection、`top-k` 模式和 query-only Context Builder 行为。
- `search_wiki.py` 变为 Discovery Catalog v2；`build_query_context.py` 变为必需 `--concept` 的 Hydration Envelope v2。
- Plugin 和模板版本提升到 `1.1.0`；OKF/Profile 数据版本不变。

## Implementation units

### U1 — Discovery Catalog v2

- Requirements: R18-R19、R22
- Dependencies and accepted-design pointers: design §4-5
- Affected modules and mutation: Runtime search public API、CLI、exports、search tests
- Entry / exit conditions: Search v2 已有中文排序；完成后只返回候选元数据且不存在 `content`，repository/schema/limit 信息稳定。
- Focused verification: 中文、空结果、限制、稳定性、byte-diff、Source Summary 抑制测试。
- Recovery checkpoint: Runtime 搜索私有评分 helper 不变，可独立回退公开 envelope 组装。

### U2 — Explicit Hydration Envelope v2

- Requirements: R18-R20、R22
- Dependencies and accepted-design pointers: U1 candidate IDs；design §6
- Affected modules and mutation: Context Builder、CLI、tests
- Entry / exit conditions: 必须显式 1–8 个 Concept ID；完整页面按调用顺序返回；超限/非法路径原子失败；不搜索、不读 Raw。
- Focused verification: 顺序、去重、完整性、数量/字符、隐藏/保留/symlink、无 mutation。
- Recovery checkpoint: Hydration 是独立 public function，可在不动交易/Raw Runtime 的情况下回退。

### U3 — Skill、维护契约与版本切换

- Requirements: R10-R14、R17-R24
- Dependencies and accepted-design pointers: U1-U2 schema；design §7-8
- Affected modules and mutation: Query Skill/Contract、Maintainer Skill/workflows、doctor、Manifest、模板、packaging tests
- Entry / exit conditions: 两个 Skill 只呈现唯一两阶段路径；无旧命令语义或 70% 规则；所有发行身份为 1.1.0。
- Focused verification: 静态 contract tests、Plugin doctor、Claude validator。
- Recovery checkpoint: Skill/Manifest 改动可与 Runtime v2 一起整体回退至已发布 v1.0.0。

### U4 — 回放与交付验证

- Requirements: R2、R19-R24
- Dependencies and accepted-design pointers: U1-U3
- Affected modules and mutation: tests 与只读外部 sofa4 fixture；不修改目标 Wiki
- Entry / exit conditions: 扩展点、架构、JVM 要求完成 discover→semantic select→hydrate；类加载返回知识缺口而不加载无关候选或直搜 Raw；fallback 由独立 fixture 验证；前后目标 Wiki 摘要一致。
- Focused verification: unittest、compileall、Ruff、diff check、Plugin validator、doctor、真实回放。
- Recovery checkpoint: 若回放暴露契约缺口，返回对应实现单元修复并重跑全量验证。

## Verification contract

- Required: `python3 -m unittest discover -s tests -v`、`python3 -m compileall -q scripts tests`、`PYENV_VERSION=3.10.16 ruff check scripts tests`、`git diff --check`。
- Required: Discovery 无正文、Hydration 仅显式完整页面、Raw fallback 边界、双仓库 byte identity。
- Required: sofa4 四查询回放（3 个 compiled hit、1 个 knowledge gap）及回放前后全文件摘要一致。
- Preferred: Claude 官方 Plugin validator、Codex 官方只读 validator；不存在的 validator 作为环境限制报告，不以 doctor 冒充。
- Experiential acceptance: 当前用户基于最终流程和真实回放摘要验收；不阻止本地工程完成，但发布前必须明确接受。

## Risks and recovery

- LLM 可能选错候选；Catalog 提供 description/snippet/provenance，Skill 要求选择最少充分页面并把 score 仅作排序，缺口由维护改进而非 Runtime 阈值掩盖。
- 显式选择可能增加一次工具调用；换取更小、更可解释的 Context，且符合原始 LLM-Wiki 导航模型。
- 超长原子 Concept 会触发硬上限；调用者可减少选择或显式提高上限，长期由 Maintainer 拆分编译债务。
- 这是公开协议破坏性升级；用户明确拒绝兼容，仓库数据不迁移，恢复依赖 Plugin 版本回退。

## Definition of done

- Query 只有 Discovery → LLM Select → Hydration 主路径。
- LLM 选择前没有正文，Runtime 不依据 score 决定知识范围。
- Hydration 返回完整选中页面且字符超限原子失败。
- 普通 Query 不读 Raw；fallback 仍由已选 Concept provenance 限定。
- 两个 Skill、Runtime、Manifest、模板和测试一致为 1.1.0。
- 完整验证与代码审查无阻断项；原工作树不被修改，且没有 commit、push、PR 或发布。
