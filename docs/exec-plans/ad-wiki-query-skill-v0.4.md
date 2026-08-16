# Implementation Plan: AD-Wiki 独立只读 Query Skill v0.4

Product Contract: `docs/product-specs/ad-wiki-repository-local-scope.md`

Technical Design: `docs/designs/ad-wiki-query-skill.md`

Requirements: R1-R6, R10-R14, R16-R19

Commit policy / authority: `local-complete-only`; 用户于 2026-08-16 要求开始实施，但本轮没有新增 commit、push 或 PR 授权

## Implementation decisions

- 发布 Plugin `0.4.0`，保持 OKF `0.2`、AD-Wiki Profile `0.1` 和现有 Wiki 数据不变。
- 新增独立 `ad-wiki-query`，独占面向用户的只读 Query Contract；Maintainer 删除公开 Query。
- 新增一个宿主无关、确定性、只读的 Context Builder。两个 Skill 共享该代码，不共享完整 Prompt，也不互相调用。
- 保留 `search_wiki.py` 作为低层兼容入口，并为结果增加 additive `total` 字段。
- 不增加 MCP、App、HTTP/SDK Adapter、Raw 自动注入、远程服务或跨仓库能力。

## Implementation units

### U1 — 固定 Context Envelope 和只读边界

- Requirements: R2-R5, R18-R19
- Affected modules: `tests/test_runtime.py`、`tests/test_cli.py`
- Exit conditions: Envelope v1 的字段、排序、字符预算、截断、参数范围和仓库 byte-diff 都由失败优先测试固定
- Focused verification: runtime/CLI unit tests

### U2 — 实现共享 Retrieval/Context Core

- Requirements: R2-R5, R18-R19
- Affected modules: `scripts/ad_wiki/runtime.py`、`cli.py`、`__init__.py`、`scripts/build_query_context.py`
- Exit conditions: 显式 `--repo` 和 query 可产生稳定 Envelope；无写入参数或运行状态副作用
- Focused verification: Context unit、真实 CLI、无匹配与边界错误

### U3 — 分离 Query 与 Maintainer Skill

- Requirements: R10-R12, R14, R16-R19
- Affected modules: `skills/ad-wiki-query/`、`skills/ad-wiki-maintainer/`
- Exit conditions: Query 只负责带引用回答和 writeback candidate；Maintainer 只负责 Init/Ingest/Writeback/Lint/Migrate，并用 Builder 做影响分析
- Focused verification: 两个 Skill validator、静态职责测试、fresh-context forward test

### U4 — 同步 0.4.0 发行与设计文档

- Requirements: R1, R10-R14, R17-R19
- Affected modules: 双 Manifest、模板 provenance、Profile/迁移说明、Product Contract、Technical Design、canonical team workflow
- Exit conditions: 两端发布身份、Runtime、模板和文档一致；团队 Wiki 无迁移
- Focused verification: packaging tests、JSON parse、文档/版本检索、`git diff --check`

## Verification contract

- Focused evidence: `python3 -m unittest tests.test_runtime tests.test_cli tests.test_packaging`。
- Full evidence: `python3 -m unittest discover -s tests -v`、`python3 -m compileall -q scripts tests`、所有官方 Plugin/Skill validators。
- Behavioral evidence: 临时 Wiki 中 Builder 前后全部文件 hash 一致；Context Envelope 包含语言、领域、Concept 正文、来源和截断状态。
- Cross-host evidence: 两个 Manifest 发现相同的两个根级 Skill，并共享唯一 Runtime。
- Forward evidence: 新上下文 Agent 仅依据 Query Skill 和样例 Wiki回答普通问题，必须调用 Builder、引用来源、保持只读并正确处理 writeback candidate。
- Scope protection: `.agents/skills/`、`.claude/`、`docs/designs/ad-wiki-scale-platform.md` 和 `docs/designs/ad-wiki-team-workflow.md` 中任务前已有的规模化平台 hunk 不属于本实现；不得覆盖或误报。

## Risks and recovery

- Query 与 Maintainer 再次职责重叠：由 Skill 静态测试和独立 references 阻断。
- Context 过大或静默缺页：由双预算和显式 `truncated` 阻断。
- 查询意外写入：Builder 没有写入口，且 byte-diff 测试覆盖真实仓库。
- 版本漂移：packaging test 比较双 Manifest、Runtime 和模板 provenance。
- 回滚只需移除新 Skill/Builder 并恢复 `0.3.0` 元数据；不需要迁移或恢复团队 Wiki。

## Definition of done

- 两个宿主发现 `ad-wiki-query` 与 `ad-wiki-maintainer`；两者职责清晰且无 Skill-to-Skill 依赖。
- Context Envelope v1 稳定、可追溯、预算受控、字节只读。
- Maintainer 在 Ingest/Writeback 中复用 Context Builder，但不提供普通问答。
- Plugin `0.4.0` 的双 Manifest、Runtime、模板和文档一致，OKF/Profile 不变。
- 全量测试、编译、官方 validators、端到端和 forward test 通过。
- 代码审查没有未解决的任务内高置信度缺陷；本轮停在 `local-complete`。
