# Technical Design: AD Code Wiki 结构智能 v1.5

Design identity: `ad-code-wiki-structural-intelligence-v1.5-accepted`

Product Contract: in-run `code-wiki-structural-intelligence-2026-08-22`

Requirements covered: R-CI1–R-CI15

Upstream design: `docs/designs/ad-code-wiki-full-compilation.md`

Research basis: Graphify `v8` commit `b2cd36267456c166788c95be6e68574064a92a42` 的公开架构、AST/graph schema、ID、cache/incremental、affected/query、wiki export 和安全实现；本设计只吸收可迁移思想，不复制代码、不调用 Graphify、不读取 Graphify 产物。

Authority: 用户于 2026-08-22 明确要求 AD Wiki 不依赖 Graphify，并认可 Java/SOFA-first、自建结构索引、允许直接依赖 `tree-sitter` 与 `tree-sitter-java`、Extractor 协议可扩展、其他语言后续增加的推荐边界。

Design status: accepted；用户于 2026-08-22 以“开始实施”明确接受本设计并授权本地实现。

## 1. Current behavior, constraints, and invariants

已接受的 `1.4.0` Code Wiki 设计和当前本地实现具备：

- 一个显式 AD Wiki + 一个 latest clean Git code repo；
- 全基础 Concept inventory、五类终态、checkpoint/resume；
- 模型通过文件搜索定位实现、调用方和测试；
- revision/path/symbol code refs；
- Companion、Mermaid、核心代码、managed base link；
- feedback 与语义 Writeback 分离；
- exact staged set 和一次原子 Apply。

当前不足：

1. 全库 Concept 的代码候选主要由模型和文本搜索发现，没有确定性符号/调用图。
2. `code_refs` 的 symbol 是自由文本；跨运行无法可靠判断符号移动、签名变化或删除。
3. 没有 `EXTRACTED / INFERRED / AMBIGUOUS` 证据层级，无法区分源码直接关系和解析推断。
4. 每次新 revision 都重新搜索，缺少内容哈希 cache、成功 manifest、增量更新和删除 pruning。
5. 没有 path/explain/affected 查询 seam，变更文件不能稳定映射到受影响 Concept。
6. 文件大小、binary/control-char 和 snippet budget 只有局部防护，没有统一结构索引输入限制。

必须保留：

- Concept-first：结构图只提供候选导航和可审计关系，不成为 Wiki 真源或页面边界。
- 文档优先：对外契约仍来自文档；代码图不能自动纠正文档。
- Query/Writeback 治理：代码查询结果不自动写回；语义修复继续单独授权。
- 基础能力独立：Query、Maintainer 和无 Code Wiki 的基础 Wiki 不加载 AST 依赖。
- Code repo 只读：不执行目标代码、构建、测试、hooks 或脚本。
- 没有 Graphify runtime/package/CLI/graph.json 依赖，也不复制其源码。

## 2. Confirmed product requirements

- **R-CI1 — 独立实现**：AD Wiki 自建结构索引，不依赖 Graphify。验收：发行依赖、命令、Skill、Runtime 和测试均不引用 Graphify 包、CLI 或产物；设计来源只作为文档引用。
- **R-CI2 — Java/SOFA-first**：一期必须正确覆盖 Java 源码、Java 测试、Maven POM/XML 和 `.properties` 配置；其他语言不是发布门槛。验收：SOFA 类、接口、方法、构造器、字段、注解、import、extends/implements、调用、配置和测试关系在 fixture/真实试点可查询。
- **R-CI3 — 可扩展 Extractor**：语言/配置提取器共享一个稳定 Fragment 协议。验收：Java、Maven/XML、Properties 三个 provider 不修改 graph/cache/query 核心；新增语言只注册 provider 和 tests。
- **R-CI4 — 确定性结构图**：相同 repo bytes、revision、extractor/schema 版本产生字节稳定的 nodes/edges/manifest。验收：顺序、ID、位置、枚举和 JSON 输出 deterministic。
- **R-CI5 — 稳定符号身份**：每个节点使用保留大小写的 `language:kind:path#qualified-symbol` ID。验收：repo 移动不改变 ID；Java 大小写不同的合法符号不合并；重跑幂等。
- **R-CI6 — 关系证据等级**：边必须标记 `EXTRACTED | INFERRED | AMBIGUOUS`，不使用主观浮点信任分。验收：直接 import/extends/call 与唯一解析/多候选解析被正确区分并可追溯到 source location。
- **R-CI7 — Schema-first validation**：任何 Fragment/graph/cache 在消费或发布前验证节点、边、端点、位置、枚举、大小和引用完整性。验收：dangling、duplicate、invalid enum、越界位置和 malformed artifact 原子失败。
- **R-CI8 — 有界摘要与词表**：文件和类型节点提供 deterministic、versioned、长度有界的责任摘要与实际 symbol vocabulary。验收：摘要不调用 LLM、不替代源码；模型只能从真实 vocab 选择候选扩展词。
- **R-CI9 — 图查询能力**：Runtime 提供 search、explain、path、BFS/DFS subgraph 与 reverse affected；输出受节点/边/字符预算控制。验收：查询结果携带 ID、relation、evidence、path/location，零匹配/歧义诚实返回。
- **R-CI10 — 内容哈希 cache**：每个源文件按 bytes + extractor/schema/grammar/summary version 计算 cache key。验收：未变文件不重解析，配置/版本变化使 cache miss，损坏 cache 不被静默复用。
- **R-CI11 — 原子增量 manifest**：新 revision 识别 added/changed/deleted/unchanged，先更新 fragments，再全局重解引用，成功后原子发布 graph/manifest。验收：中断不污染上一个成功索引；删除文件节点/边被 prune。
- **R-CI12 — 受影响 Concept**：Validated Code Wiki bindings 记录 Concept↔symbol IDs；changed symbol/file 可通过 reverse traversal 产生待刷新 Concept。验收：增量运行只重新评估受影响 Concept，无法证明安全时回退全 Concept 评估。
- **R-CI13 — Code Wiki 证据绑定**：`code_refs` 增加 `symbol_id/relation/evidence/source_location`，Checkpoint 必须验证这些引用存在于当前结构图。验收：Mermaid/原理仍由模型综合，但核心关系可追溯且 revision 一致。
- **R-CI14 — 输入和资源安全**：统一限制 file count、单文件 bytes、graph bytes、snippet lines/chars、binary/control chars、symlink/path、生成/vendor/secret paths。验收：超限失败可操作，不能形成 memory bomb 或泄露明显秘密。
- **R-CI15 — 治理不回退**：结构索引不生成社区/God Node Wiki、不清空目录、不 fuzzy merge 代码符号、不自动保存 Query、feedback 或 correction。验收：所有 live Wiki 写入仍由 `ad-code-wiki` staged transaction 和标准 Writeback 控制。

## 3. Decision summary

1. 新增自有 `ad_wiki.code_index` 子系统；它是 `ad-code-wiki` 的内部导航能力，不是第四个 Skill。
2. 使用独立、锁定的 `code-index/` Python environment，直接依赖 `tree-sitter` 与 `tree-sitter-java`；Plugin 的 Query/Maintainer/普通 Code Wiki metadata 命令仍保持 stdlib-only。
3. `1.5.0` 以显式 `--structural-index` 增加 additive structural mode；未启用时保持 `1.4.0` model-only 路径。启用后依赖环境缺失必须 fail closed，返回安装/缓存提示，不静默降级为伪确定性 AST。SOFA 验收必须启用 structural mode。
4. Extractor protocol 一期实现 `JavaExtractor`、`MavenXmlExtractor` 和 `PropertiesExtractor`；未来语言只扩展 providers。
5. 结构索引、cache 和 bindings 是可重建的本地运行视图，保存在 `.ad-wiki/cache/code-index/`，由目录内 `.gitignore` 隔离，不进入 OKF Bundle/Git 默认提交。
6. 成功 run 在 `run.json` 只持久化 code-index manifest digest、schema/extractor versions、graph metrics 和 bindings digest；不持久化绝对路径或整张图。
7. `ad-code-wiki` 先使用结构索引查询候选 subgraph，再读取候选原始源码/测试完成语义验证；图关系不能直接成为最终 Wiki 主张。
8. 增量刷新只影响下一次 Code Wiki run；不会建立后台 watcher、hook、daemon 或自动修改 Wiki。
9. Plugin 目标版本 `1.5.0`；OKF `0.2`、AD-Wiki Profile `0.1` 和 Source Registry v1 不变。

## 4. Dependency and packaging boundary

### 4.1 Isolated owned environment

```text
code-index/
├── pyproject.toml
└── uv.lock
```

依赖精确锁定兼容区间：

```toml
dependencies = [
  "tree-sitter==0.25.2",
  "tree-sitter-java==0.23.5",
]
```

结构命令通过统一 launcher 执行：

```bash
uv run --frozen --project <plugin-root>/code-index \
  python3 <plugin-root>/scripts/<code-index-command>.py ...
```

规则：

- 一期要求 `uv`；缺失时返回安装提示，不修改全局 Python。
- `--frozen` 禁止运行期间漂移 lock；依赖未在本机缓存且无法联网时明确失败。
- 团队离线环境可以预热 uv cache 或内部镜像；不把下载器、wheel 或平台二进制复制进 Plugin。
- 基础 Query/Maintainer/Init/Lint 不调用 launcher，因此不承担额外依赖和启动成本。
- 不声明 Graphify、NetworkX、RapidFuzz、Leiden、向量或 LLM SDK 依赖。

### 4.2 License boundary

本实现根据公开行为和通用图/AST思想独立编写，不复制 Graphify 源码。若未来确需复制 Apache-2.0 实现片段，必须作为新的授权事项处理 LICENSE/NOTICE；本迭代不这样做。

## 5. Module structure and ownership

```text
scripts/ad_wiki/code_index/
├── __init__.py
├── model.py             # schema dataclasses/enums/JSON validation
├── ids.py               # stable case-preserving IDs
├── extractors.py        # Extractor protocol + registry
├── java.py              # tree-sitter Java facts/fragments
├── maven_xml.py         # stdlib XML Maven/config facts
├── properties.py        # deterministic .properties facts
├── resolve.py           # global symbol/import/call resolution
├── graph.py             # fragment merge/prune/stable graph assembly
├── summaries.py         # bounded deterministic file/type summaries + vocab
├── cache.py             # content-addressed fragments and atomic manifest
├── query.py             # search/explain/path/BFS/DFS/affected
└── security.py          # file/binary/size/path/control-char guards

scripts/
├── build_code_index.py
├── query_code_index.py
├── inspect_code_impact.py
└── publish_code_bindings.py
```

`code_index` 对外只暴露三个深入口：

- `build_or_update_index(code_root, cache_root, revision) -> IndexReceipt`
- `query_index(cache_root, QueryRequest) -> SubgraphResult`
- `affected_bindings(cache_root, ChangedSet) -> ImpactResult`

内部 provider、Network-free graph representation、cache 文件布局和并行调度不成为 Skill API。

`ad_wiki.code_wiki` 继续拥有 Concept inventory/checkpoint/finalize/Apply。它只消费上述接口，不直接解析 AST 或操纵 cache。

## 6. Extractor protocol

```python
class Extractor(Protocol):
    name: str
    version: str
    languages: tuple[str, ...]

    def supports(self, path: Path) -> bool: ...
    def extract(self, path: Path, *, root: Path, content: bytes) -> Fragment: ...
```

`Fragment`：

```json
{
  "schema_version": "1",
  "extractor": {"name": "java", "version": "1", "grammar": "tree-sitter-java/<version>"},
  "source": {"path": "src/Foo.java", "sha256": "...", "bytes": 1234},
  "nodes": [],
  "edges": [],
  "unresolved": []
}
```

Provider 规则：

- Java：package、import、class/interface/enum/record/annotation、method/constructor、field、annotation use、extends/implements、direct call facts、test declarations。
- Maven/XML：artifact/module/dependency/plugin/profile/property 与相关 source location；不执行 entity/include 或 Maven interpolation。
- Properties：key/value location、placeholder references；value 疑似 secret 时只记录 key/type，不记录值。
- unsupported file 不报 extraction failure，只进入 manifest 的 `unsupported` 计数；Java/SOFA 发布验收要求关键实现/配置文件被上述 providers 覆盖。
- Provider 输出只含当前文件直接事实；跨文件解析统一在 `resolve.py` 完成。

## 7. Stable node identity

Java 是大小写敏感语言，因此不复制 Graphify 的 casefold ID 算法。统一构造器保留大小写并只规范化：

- repo-relative POSIX path；
- Unicode NFC；
- 去除 `.`/重复分隔；
- kind 固定 enum；
- Java 参数采用语法层可确定的 erasure type token，保留源码中是否 fully-qualified 的写法并规范化空白；全局解析不得重写节点 ID，只影响 relation target/evidence。

ID examples：

```text
java:file:src/main/java/com/acme/Foo.java
java:type:src/main/java/com/acme/Foo.java#com.acme.Foo
java:method:src/main/java/com/acme/Foo.java#com.acme.Foo.start(java.lang.String)
java:field:src/main/java/com/acme/Foo.java#com.acme.Foo.state
xml:maven:pom.xml#com.acme:service
properties:key:conf/sofa.properties#sofa_module_start_up_parallel
unresolved:java:src/main/java/com/acme/Caller.java#start/1
```

不进行跨文件 fuzzy merge。Exact ID duplicate 必须按同一 source/location 幂等合并；不同 source 产生相同 ID 是 schema error，不选择“winner”。

## 8. Graph schema and evidence

### Node

```json
{
  "id": "java:method:...",
  "label": "Foo#start(String)",
  "kind": "method",
  "language": "java",
  "source_file": "src/.../Foo.java",
  "source_location": {"start_line": 42, "end_line": 57},
  "summary": "Starts the component and publishes lifecycle state.",
  "summary_generated_by": "deterministic",
  "summary_version": 1
}
```

### Edge

```json
{
  "source": "java:method:...Caller#run()",
  "target": "java:method:...Foo#start(String)",
  "relation": "calls",
  "evidence": "INFERRED",
  "source_file": "src/.../Caller.java",
  "source_location": {"start_line": 88, "end_line": 88}
}
```

Evidence：

- `EXTRACTED`：语法树直接给出确定 target，例如 import、extends、implements、contains、完整限定名调用。
- `INFERRED`：通过 package/import/type/member index 得到唯一 target。
- `AMBIGUOUS`：存在多个合法 target 或 receiver/type 无法确定。此时 target 指向稳定 `unresolved` node，metadata 保存 bounded candidate IDs；不得任选一个真实 target。

不使用 confidence float。每条 edge 必须有 source file/location；无位置关系不得写入 graph。

## 9. Build, resolution, and deterministic parallelism

```text
secure file inventory
→ hash + cache lookup
→ per-file extraction (bounded ProcessPool)
→ stable fragment validation/sort
→ merge unchanged + changed fragments
→ prune deleted file nodes/edges
→ rebuild global declaration/import/member indexes
→ resolve cross-file facts
→ validate referential integrity
→ generate bounded summaries + vocab
→ write versioned graph artifact
→ atomically publish manifest.json pointer last
```

- 默认 worker 数 `min(4, cpu_count)`；测试可以固定为 1。并行完成顺序不影响输出，所有 merge/output 按 path/ID/relation/location 排序。
- 全局 resolution 每次重跑，避免 changed import 导致未变 fragment 的旧 target 残留；文件 AST extraction 才按 hash 增量。
- 不构建 community、Leiden、centrality 或 fuzzy dedup；这些不是 Concept-first 候选发现的必要条件。
- graph 使用自有 JSON adjacency/index 表，不引入 NetworkX。

## 10. Cache and manifest

```text
.ad-wiki/cache/code-index/<repo-key>/
├── .gitignore              # contains '*'; the whole runtime cache self-ignores
├── manifest.json           # last successful publish
├── graphs/
│   └── <graph-sha256>.json # immutable structural graph generations
└── fragments/
    └── <cache-key>.json
```

`repo-key = sha256(normalized remote；无 remote 时使用 repo basename + sorted Git root commits)[:16]`；绝对 code root 不写入 artifact。

Fragment key：

```text
sha256(
  file_bytes
  + schema_version
  + extractor_name/version
  + grammar_version
  + summary_version
)
```

Manifest：

```json
{
  "schema_version": "1",
  "revision": "<git-sha>",
  "source": "<normalized-remote-or-urn>",
  "extractors": {"java": "1", "maven-xml": "1", "properties": "1"},
  "files": {"src/Foo.java": {"sha256": "...", "fragment": "..."}},
  "unsupported": [],
  "graph_file": "graphs/<graph-sha256>.json",
  "graph_sha256": "...",
  "node_count": 0,
  "edge_count": 0,
  "ambiguous_edge_count": 0,
  "published_at": "..."
}
```

- graph 以 content hash 文件名原子写入，不覆盖旧 generation；manifest 经 temp+fsync+`os.replace` 最后发布指针。
- crash 时上一个 manifest 仍指向旧 graph；未引用的新 generation/孤立 temp 后续清理。
- cache JSON 损坏视为 miss 并聚合 warning；不能静默反序列化失败后宣称 hit。
- cache 可以删除并全量重建，不进入 Bundle migration/rollback。

## 11. Deterministic summaries and vocabulary

只为 file/type 节点生成摘要，最长 300 Unicode chars，信号顺序：

1. module/Javadoc 首句（清除 HTML/control chars）；
2. public/exported types and methods；
3. import/dependency categories；
4. dominant extracted relations；
5. test/config role。

摘要字段携带 `summary_generated_by: deterministic` 与 `summary_version`，不调用模型。

Vocab 从 node labels、qualified names、package segments、configuration keys 产生；camelCase/PascalCase/underscore 分词但保留原 token。模型做 Concept query expansion 时：

- 最多选择 16 个 vocab 中真实存在的 token；
- 不得从训练记忆发明 code token；
- 选择的 token、命中 node 和零匹配原因写入 run checkpoint，供审计。

## 12. Query, path, explain, and affected APIs

### Request

```json
{
  "mode": "search|explain|path|bfs|dfs|affected",
  "tokens": ["extension", "register"],
  "source_id": null,
  "target_id": null,
  "relations": ["calls", "imports", "extends", "implements", "references"],
  "max_depth": 3,
  "max_nodes": 200,
  "max_edges": 500,
  "max_chars": 20000
}
```

### Response

```json
{
  "schema_version": "1",
  "mode": "bfs",
  "revision": "...",
  "matched_tokens": [],
  "start_nodes": [],
  "nodes": [],
  "edges": [],
  "truncated": false,
  "ambiguities": [],
  "diagnostics": []
}
```

规则：

- search 按 exact ID/path/label/token overlap 排序；分数只用于本次候选排序，不持久化为知识 trust。
- explain 返回一个节点的 bounded incident relations。
- path 使用最短无权路径；没有路径诚实返回。
- BFS/DFS 遵守 depth/node/edge/char 四重预算。
- affected 默认沿 calls/references/imports/extends/implements/uses 的反向边，并返回关系发生位置。
- 多个同名节点不自动选一个；返回 ambiguity 和候选 IDs。
- 查询不写 graph、Wiki、query log 或 host memory。

## 13. Code Wiki integration

`prepare_code_wiki.py` 增加显式 `--structural-index`。只有启用时运行 structural index preflight：

```text
clean Git identity
→ build/update code index
→ persist manifest digest/metrics in run.json.code_wiki
→ generate full Concept inventory
```

未传 `--structural-index` 时保持 `1.4.0` 的 model-only candidate discovery 和 code_refs v1，不创建 cache/graph/bindings。传入 flag 后，从 Prepare 到 Finalize 必须始终绑定同一 manifest digest；依赖或索引失败不得退回 model-only 并继续同一 run。

每个 Concept：

```text
read full Concept
→ select bounded real vocab tokens
→ query structural subgraph
→ read candidate source/callers/tests
→ validate or reject graph match
→ compile Companion/checkpoint
```

`code_refs` v2：

```json
{
  "symbol_id": "java:method:...",
  "path": "src/.../Foo.java",
  "symbol": "Foo#start(String)",
  "kind": "implementation",
  "relation": "calls",
  "evidence": "EXTRACTED",
  "source_location": {"start_line": 42, "end_line": 57}
}
```

Checkpoint 必须验证：

- symbol ID 存在于 pinned graph；
- path/symbol/location 与 node 一致；
- relation/evidence 若提供，对应 edge 存在；
- graph revision/manifest digest 与 run 一致；
- 核心代码 excerpt 仍从原始 code file 读取并校验 line span，不从 graph summary 复制。

Finalize 生成 bindings digest：

```json
{
  "concepts/lifecycle": ["java:type:...", "java:method:..."],
  "concepts/extension-point": ["java:method:..."]
}
```

Finalize 把 pending bindings 和 digest 写入 run state，但不更新 successful cache。`apply_run.py` 返回 `VALIDATED` 后，Skill 调用 `publish_code_bindings.py --repo <wiki> --run-id <id>` 原子发布 bindings；Apply 失败不发布。Bindings 发布失败不回滚已经验证的 Wiki，而是报告 residual，并让下次 structural run 安全回退全 Concept 评估。

## 14. Incremental refresh and impact

下一次 Code Wiki run：

1. 比较 successful manifest 与当前 clean revision files；
2. 解析 added/changed，prune deleted，重建 global resolution；
3. 计算 changed nodes/edges；
4. 通过 reverse affected traversal 得到受影响 symbol set；
5. 通过 last validated bindings 得到 affected Concept IDs；
6. 若 graph/schema/extractor version 改变、bindings 缺失/损坏、ambiguous impact 或 affected 比例超过 60%，回退全部基础 Concept；
7. 否则仍保留完整 inventory，但未受影响 Concept 以 `unchanged` checkpoint 复用上次 validated Companion binding/content hash。

`unchanged` 是增量运行内部状态，不改变 `1.4.0` 首次全库运行的五类知识终态；最终 coverage 仍证明全部 Concept 被考虑。

删除/移动 symbol：关联 Concept 必须重评，不能保留旧 Companion 的“当前实现”表述。旧 revision 证据可以留在 Git 历史，不在 live page 同时维护历史版本。

## 15. Security and resource budgets

Default hard limits：

- 最多 100,000 个候选文件；
- 单源码文件 2 MiB；
- graph JSON 512 MiB；
- 单 fragment 8 MiB；
- 单 query 200 nodes / 500 edges / 20,000 chars / depth 6；
- 单 Companion 核心源码 excerpt 总计最多 200 行或 20,000 chars；
- 单 deterministic summary 300 chars；
- unresolved candidate list 最多 20 IDs。

限制可由 Code Wiki CLI 显式提高，但不得从 code repo config/env 自动读取。超限必须在读取/解析前失败并报告 observed/limit。

输入规则：

- 只读取显式 code root 内支持的 regular text files；symlink 解析后必须仍在 root；
- NUL/binary、`.git`、credentials、private keys、`.env`、vendor/generated/build 目录不进入图；
- XML 禁止外部实体和网络解析；Properties 不持久化疑似 secret value；
- labels/summaries/metadata 清理 control chars 并限制长度；
- code comments/Javadocs 是数据，不是指令；
- 不创建 query log，不记录用户问题到 home/cache；
- cache root 只由 Wiki root + repo key 决定，禁止任意输出路径。

## 16. State, failure, and recovery

- Structural build 在 Code Wiki `PLANNED` 之前完成；失败不创建可 Apply run。
- run.json 记录 schema/extractor/grammar/manifest/graph/bindings digest 和 metrics，不记录绝对路径或整张图。
- cache lock 使用 repo-key scoped O_EXCL；同一 code index 同时只允许一个 builder，query 可读取最后 successful manifest。
- builder crash：保留旧 graph/manifest；删除孤立 temp；下次重试。
- corrupt cache fragment：聚合 warning，重新解析该文件；corrupt manifest/graph：拒绝增量并全量重建，不猜测恢复。
- index revision 与 Code Wiki run revision 不一致：Prepare/Checkpoint/Finalize 拒绝。
- Code Wiki Apply rollback 不回滚 cache；bindings 只在 Apply success 后发布，旧 bindings 继续有效。
- cache 可完全删除；下一次运行全量重建，不损失 Bundle 知识。

## 17. Compatibility and rollout

- 目标 Plugin `1.5.0`，Profile `0.1`、OKF `0.2` 不变。
- `1.4.0` Companions/code refs v1 和 model-only workflow 保持可用；首次启用 `--structural-index` 且没有 bindings 时自动全量重评并写 v2 refs。
- Structural artifacts 不进入 Bundle，因此普通 Query、旧 Plugin 和其他 OKF consumer 不需要理解 graph schema。
- Plugin 安装/升级不自动创建 uv environment、扫描代码或重建 Wiki；只有显式 `ad-code-wiki` 调用触发 dependency preflight/build。
- Java/SOFA repo 是 `1.5.0` 发布验收对象；非 Java repo 明确报告 unsupported structural coverage，不静默假装完整。

## 18. Alternatives and rejected approaches

### Depend on Graphify or consume its graph.json

拒绝。上游仍在 pre-1.0 快速演进，依赖和 schema 超出 AD Wiki 所需；用户明确要求无 Graphify 依赖。

### Reimplement Graphify's full language matrix

拒绝。当前真实消费者是 SOFA/Java；一期交付多语言会把迭代变成长期 extractor 平台。协议先稳定，其他语言按需求加入。

### Keep zero third-party dependencies

拒绝用于 structural mode。没有 parser dependency 无法诚实提供 AST 调用/继承关系；模型/regex 不能冒充确定性 AST。基础 Wiki 能力仍保持零新增依赖。

### Use communities/centrality as Wiki page boundaries

拒绝。页面边界由已有 Concept 决定；图拓扑只导航候选和影响范围。

### Fuzzy merge code symbols

拒绝。相似类/方法可能是合法并行实现；只允许 exact stable ID 和语义阶段人工/模型判断。

### Auto-save code queries/reflections into Wiki or graph

拒绝。查询记录可能含敏感问题，且绕过 Writeback；所有反馈继续受治理。

### Build an interactive graph UI

延期。结构 JSON、CLI query 和 Code Wiki 页面已满足当前用户结果；HTML/Graph UI 不是 Code Wiki 完整性的必要条件。

## 19. Risks and verification approach

### Parser/grammar drift

通过 uv lock、grammar version in cache key、fixture corpus 和 full rebuild on version change 控制。

### Java call resolution false positives

直接语法 facts 标 EXTRACTED；唯一索引解析才标 INFERRED；多个候选进入 unresolved/AMBIGUOUS，不选择最高分。真实 SOFA 调用链抽样验收。

### Incremental stale edges

Changed fragments merge 后总是全局重解引用并做 referential-integrity validation；manifest 最后发布；删除文件 prune。

### Cache/graph size

前置文件/bytes cap、content-addressed fragments、bounded summaries/query、graph cap；性能 benchmark 记录 files/nodes/edges/time/cache-hit/memory。

### New dependency harms base Plugin

隔离 `code-index/` uv environment，只有结构索引命令调用；现有 1.4 tests 在无 tree-sitter environment 下仍必须全过。

### Required verification

- ID/property tests：case-sensitive Java symbols、Unicode NFC、repo move、signature、collision、idempotency。
- Extractor fixture：Java declarations/imports/inheritance/calls/annotations/tests；Maven modules/dependencies/plugins/properties；Properties placeholders/secrets。
- Schema negative tests：dangling endpoints、invalid evidence/location、duplicate IDs、oversize/binary/symlink/control chars。
- Determinism：worker=1/4、不同 completion order、不同 checkout roots 产出相同 graph bytes。
- Incremental：no-op cache hit、add/change/delete/rename、grammar/schema version miss、corrupt fragment/manifest、atomic crash recovery。
- Query：exact/path/label ambiguity、vocab-only expansion、BFS/DFS/path/explain/affected、budget/truncation、zero-match。
- Integration：code_refs v2 index binding、wrong revision/symbol/edge拒绝、bindings only after Apply、full fallback threshold。
- Regression：无 uv/tree-sitter 时所有非 structural AD Wiki commands/tests/validators 保持通过。
- Experiential：完整 SOFA Wiki + latest SOFA repo 比较 `1.4` model-only 与 `1.5` structural navigation 的匹配准确率、needs-review/no-code-match、读取文件数和耗时；用户审阅典型 Mermaid/核心代码页面。

Performance 不预设无证据的绝对 SLA。首次 SOFA 基线登记 files/nodes/edges/wall time/peak RSS；后续同规模 fixture 或 SOFA revision 的性能回归预算为 wall time/peak RSS 不恶化超过 20%，除非准确率证据支持并由用户接受。

## 20. Scope deltas and evidence

相对 accepted `1.4.0` Design，本迭代新增：

- owned optional dependency environment；
- Java/SOFA structural extractor protocol；
- local graph/cache/manifest/bindings durable runtime views；
- graph query/affected interfaces；
- incremental Code Wiki refresh。

继续排除：Graphify dependency、docs/media graph extraction、multi-language release obligation、communities/fuzzy dedup、interactive graph UI、query logging、auto writeback、watcher/daemon/central service。

Research evidence：

- Graphify architecture/pipeline/schema/confidence：`ARCHITECTURE.md`；
- AST/docs separation、content hash cache、graph format：`docs/how-it-works.md`；
- stable ID single source of truth：`graphify/ids.py`；
- incremental manifest/cache design：`graphify/cache.py` 与 incremental design；
- reverse affected traversal：`graphify/affected.py`；
- schema/security constraints：`graphify/validate.py`、`graphify/security.py`；
- rejected page generation behavior：`graphify/wiki.py`；
- query expansion/traversal/self-write behavior：Codex query reference。

这些是设计输入，不是 Runtime dependency 或实现复制授权。

## 21. Decision coverage and simplicity check

- Tree-sitter dependency：由用户接受确定性 Java AST 且明确允许直接依赖驱动；隔离环境避免污染基础 Plugin。
- Extractor protocol：Java/POM/Properties 三个当前消费者证明真实变化轴；不是为假想复用提前抽象。
- 自有 graph/cache：由全库候选稳定性、增量和 affected requirements 驱动；不用 NetworkX/Graphify 减少依赖。
- Stable case-sensitive ID：由跨运行 bindings 和 Java 语义驱动；不复制不适合 Java 的 casefold 算法。
- Evidence enum：由代码直接事实、唯一解析和歧义必须可区分驱动；拒绝主观浮点 trust。
- Full global resolution after incremental fragments：比局部 edge patch 更保守，避免 stale cross-file relation；代码提取仍增量。
- Cache outside Bundle：它是可重建导航视图，不是知识；避免 Profile migration 和 query consumer coupling。
- No silent fallback：避免在缺 AST 环境时把模型结果冒充 deterministic evidence。
- No communities/UI/self-learning：当前 Concept-first 用户结果不需要，删除这些机制仍满足全部 requirements。

两个实现者不再需要自行决定依赖安装、language scope、ID/schema、evidence、cache/manifest、query/impact、incremental、安全预算、Code Wiki binding、兼容和恢复语义。剩余 helper 名、内部 JSON encoder、ProcessPool plumbing 和 fixture 文件组织属于可逆实现细节。

## 22. Open technical decisions

无。
