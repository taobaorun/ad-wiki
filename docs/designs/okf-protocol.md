# Open Knowledge Format（OKF）协议解读
> OKF 是一种面向人和 AI Agent 的开放知识表示格式。它使用 **Markdown + YAML Frontmatter + 目录与链接** 来组织知识，让知识既能被人直接阅读，也能被 Agent、搜索引擎、RAG 系统和知识图谱工具稳定消费。
>

## 一、先说结论
OKF 更准确的定位不是网络通信协议，而是一个 **Git-native 的知识内容交换与打包协议**。

它关心的是：

+ 一份知识如何落盘和分发；
+ 一个知识对象如何描述自身；
+ 知识之间如何建立链接；
+ 内容来自哪里、由谁生成和验证；
+ 内容是否仍然有效；
+ 一个业务数字是否确实按照批准的计算方式产生。

它不规定服务端、数据库、查询语言或 Agent 运行时。因此可以把它理解成：

> 用 Git 仓库管理的、同时面向人和 Agent 的数据目录与企业知识库格式。
>

<!-- 这是一张图片，ocr 内容为： -->
![OKF 从知识生产者到消费者的整体架构](https://intranetproxy.alipay.com/skylark/lark/0/2026/png/78825/1786788295007-038e9b64-afde-4736-b6de-3b4f6ba42ffa.png)

_图 1：人、Agent 和导出管道共同生产 OKF Bundle，搜索、RAG、文档 UI 和图谱工具从同一份内容中消费知识。_

## 二、OKF 要解决的问题
普通 Markdown 知识库适合人阅读，但 Agent 很难稳定回答以下问题：

1. 这份文档描述的是表、API、指标还是操作手册？
2. 它对应哪个真实系统或数据资产？
3. 内容来自哪里，具体论断引用了哪份来源？
4. 谁生成了内容，又是谁验证过？
5. 内容现在是否已经过期或废弃？
6. 某个业务数字是否真的按规定方式计算出来？

OKF 的解决思路很克制：

+ 将适合机器解析、过滤和索引的属性放入 YAML Frontmatter；
+ 将解释、Schema、示例和操作步骤放入 Markdown 正文；
+ 使用目录表达层级；
+ 使用普通 Markdown 链接表达知识关系；
+ 使用 Git 提供版本、Diff、Review、归因和分发能力。

## 三、核心模型
### 1. Knowledge Bundle
一个目录就是一个 Knowledge Bundle，也是 OKF 的分发单位。它可以是：

+ 一个 Git 仓库；
+ zip 或 tar 压缩包；
+ 大型仓库里的一个子目录；
+ 静态文件服务器上的目录树。

Git 是推荐方式，因为它天然提供历史、作者、差异比较和评审工作流。

```latex
knowledge-bundle/
├── index.md
├── log.md
├── tables/
│   ├── index.md
│   ├── customers.md
│   └── orders.md
├── metrics/
│   └── revenue.md
└── playbooks/
    └── incident-response.md
```

### 2. Concept
除保留文件外，每个 `.md` 文件代表一个 Concept，即一个独立知识单元。

Concept 既可以描述具体资产，也可以描述抽象知识：

| 类别 | 示例 |
| --- | --- |
| 具体资产 | 数据表、数据集、API、Dashboard |
| 抽象知识 | 指标定义、业务流程、政策、Playbook |
| 可执行定义 | Attested Computation |


Concept ID 是文件相对于 Bundle 根目录的路径去掉 `.md`。例如 `tables/orders.md` 的 Concept ID 是 `tables/orders`。

### 3. Frontmatter 与正文
```markdown
---
type: BigQuery Table
title: Customer Orders
description: 每行代表一笔已完成订单。
resource: bigquery://acme/sales/orders
tags: [sales, orders, revenue]
---

# Schema

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| order_id | STRING | 订单 ID |
| customer_id | STRING | 客户 ID |
| total_usd | NUMERIC | 订单金额 |
```

只有 `type` 始终必填。`title`、`description`、`resource` 和 `tags` 都是推荐字段。

类型没有中央注册表。生产方可以创建自己的类型，消费方遇到未知类型时不能拒绝文档，而应将它当作通用 Concept。生产方也可以添加任意扩展字段，消费方在往返处理时应尽量保留未知字段。

这种宽松设计降低了接入成本，但也意味着企业通常还需要自己的类型词表和质量检查规则。

## 四、目录如何变成知识图谱
OKF 使用两类关系：

1. 目录结构表达隐含的父子层级；
2. Markdown 链接表达 Concept 之间的有向关系。

```markdown
订单表通过 `customer_id` 关联
[客户表](/tables/customers.md)。
```

消费者可以把这个链接提取为 `orders → customers`。但 OKF 不会把这条边严格声明为 `joins_with`；关系语义主要来自链接周围的自然语言。

因此，OKF 是“图形结构的知识库”，但不是 RDF、OWL 那类强类型语义图谱：写作自然、门槛低，但不适合依赖严格关系类型的确定性推理。

规范还要求消费者容忍断链，因为链接目标可能是尚未补充的知识，而不是格式错误。

## 五、`index.md` 与渐进式加载
`index.md` 是保留文件，用于列出当前目录的内容：

```markdown
# Tables

- [Customer Orders](orders.md) - 已完成订单。
- [Customers](customers.md) - 客户主数据。
```

它支持 Progressive Disclosure：Agent 先读取根索引，再选择相关目录和 Concept，而不必一次性把整个知识库塞进上下文窗口。

```latex
根 index
  → 相关目录 index
    → 目标 Concept
      → 按链接继续展开
```

`log.md` 是另一个保留文件，用日期分组的自然语言列表记录更新历史，但它不替代 Git 历史。

需要注意：OKF 只定义内容导航，不定义大规模检索方案。全文搜索、Embedding、向量索引、召回、重排和权限过滤仍由消费系统负责。

## 六、v0.2 的重点：来源、信任与生命周期
### 1. 来源：`sources`
```yaml
sources:
  - id: revenue-policy
    resource: https://wiki.example.com/revenue
    title: Revenue Recognition Policy
    author: team:finance
    usage_count: 5000
    last_modified: 2026-06-18
usage_window:
  from: 2026-06-01
  to: 2026-06-30
```

每个来源必须有 `resource`。其他字段提供可信度线索：

+ `author`：来源由谁产生；
+ `usage_count`：来源在指定窗口内的使用频率；
+ `last_modified`：来源本身最后更新时间。

OKF 有意不保存统一“可信度分数”，而只保存客观信号。不同消费者可以根据自己的场景推导可信度，避免把主观、容易过期的评分固化在知识包里。

具体论断可以通过 Markdown 脚注关联 `sources[].id`。稳定 ID 不受 Agent 重排来源列表影响，比使用数组下标更安全。

### 2. 生成与验证
```yaml
generated:
  by: reference_agent/gemini-2.5-pro
  at: 2026-06-20T22:53:05Z
verified:
  - by: human:alice
    at: 2026-06-25T09:00:00Z
  - by: process:finance-nightly
    at: 2026-06-26T02:00:00Z
```

+ `generated` 表示谁生成或最后实质修改了内容；
+ `verified` 表示谁对照来源或真实资源确认过内容。

Actor 使用简单字符串约定：

| Actor | 含义 |
| --- | --- |
| `producer/version` | Agent 或工具 |
| `human:<id>` | 人 |
| `process:<id>` | 自动化流程 |


消费者据此推导三种信任级别：

| 条件 | 信任级别 |
| --- | --- |
| 没有 `verified` | unverified |
| 只有机器或流程验证 | machine-confirmed |
| 至少有人类验证 | human-reviewed |


这些级别是提示，不是访问控制或密码学证明。

### 3. 生命周期与过期
```yaml
status: stable
stale_after: 2026-12-31
```

`status` 的标准值为 `draft`、`stable`、`deprecated`，缺省视为 `stable`。当 `today >= stale_after` 时，内容被视为过期。

规范选择绝对日期而不是“90 天 TTL”，这样所有消费者都能做简单、确定性的日期比较。

## 七、Attested Computation：可信计算
这是 v0.2 最有价值、也最具野心的设计。它要解决的问题是：

> Agent 给出了一个业务数字，消费者如何确认它执行的是业务方批准的计算，而不是临时生成或改写的查询？
>

<!-- 这是一张图片，ocr 内容为： -->
![OKF Attested Computation 与信任信号](https://intranetproxy.alipay.com/skylark/lark/0/2026/png/78825/1786788297720-e95fdce1-7189-4d6b-af9a-590ad3e4ed8e.png)

_图 2：定义级信任信息与单次运行的 Attestation 链路。_

一个典型的计算定义如下：

```markdown
---
type: Attested Computation
title: Revenue for fiscal year
runtime: bigquery
parameters:
  - name: year
    type: integer
    required: true
executor:
  resource: references/skills/run-on-bq.md
  receipt: [job_id, executed_sql, result]
attester:
  resource: references/attesters/revenue.py
verified:
  by: human:finance-owner
  at: 2026-06-25T09:00:00Z
stale_after: 2026-12-31
---

# Computation

SELECT SUM(amount) AS revenue
FROM finance.recognized_revenue
WHERE fiscal_year = @year
```

运行链路是：

1. 消费者发现 `Attested Computation`；
2. Agent 只为声明过的 `parameters` 提供值；
3. Executor 执行批准的计算；
4. Executor 返回包含实际执行信息的 Receipt；
5. Attester 使用确定性代码检查实际执行内容与结果；
6. Gate 根据验证结果展示、警告或拒绝结果。

几个关键字段：

| 字段 | 作用 |
| --- | --- |
| `runtime` | 定义执行与参数绑定语义，例如 BigQuery、Postgres、dbt、Python |
| `parameters` | Agent 唯一允许填写的输入面 |
| `executor` | 说明如何执行以及应返回哪些证据 |
| `receipt` | 例如 job ID、实际 SQL、编译后 SQL 和结果 |
| `attester` | 不使用 LLM 的确定性检查代码 |


需要严格区分：

+ `verified`：确认**定义**仍符合业务政策，属于文档级、低频验证；
+ attestation：确认**本次运行**按批准方式完成，属于每次调用的运行时验证。

一个过期定义仍可能通过本次运行证明；一个刚被人审查过的定义，也仍然需要对每次执行做 Attestation。

### 当前尚未完成的部分
v0.2 明确把以下内容留给后续版本：

+ Receipt 与 Verdict 的统一线协议；
+ Attester ABI、可移植性和沙箱；
+ Attestation 缓存；
+ Looker、dbt 等语义层的标准比较方法。

因此，目前它更像“可信计算的接口约定”，还不是开箱即用的完整运行时协议。

## 八、OKF 不是什么
### OKF 不是 MCP
+ MCP 解决 Agent 如何发现和调用工具、资源；
+ OKF 解决知识内容如何组织、关联和交换；
+ MCP Server 可以把一个 OKF Bundle 暴露给 Agent。

### OKF 不是 RAG
它不规定切块、Embedding、向量数据库、召回和重排，但非常适合作为 RAG 的规范化源数据。

### OKF 不是完整知识图谱标准
它没有统一本体、强类型关系和图查询语言，也不负责逻辑一致性与冲突推理。

### OKF 不替代领域 Schema
OpenAPI、Protobuf、Avro、dbt 等仍然负责领域结构。OKF 可以引用它们，并补充业务语义、背景、使用方法和可信度信息。

## 九、一致性要求与工程含义
一个 Bundle 符合 OKF v0.2，只要求：

1. 普通 `.md` 文件包含合法 YAML Frontmatter；
2. Frontmatter 中有非空 `type`；
3. 出现 `index.md` 与 `log.md` 时符合约定。

消费者不能因为缺少可选字段、未知类型、自定义字段、断链或缺少索引而拒绝 Bundle。

这种宽松性提高了兼容性，但“符合 OKF”不等于“高质量、可信、结构完整”。生产环境通常还需要：

+ 企业级类型词表；
+ Frontmatter lint 与链接检查；
+ CI 质量门禁；
+ 来源与身份认证；
+ 权限、签名与完整性保护；
+ 搜索和索引基础设施。

## 十、适合与不适合的场景
### 适合
+ 数据目录、指标口径和数据产品文档；
+ 架构知识、ADR、Runbook 与 Playbook；
+ 面向编码 Agent 的代码库知识；
+ 将企业 Wiki 或数据平台元数据导出为可移植知识包；
+ 作为 RAG 和 Agent 上下文系统的规范化输入层。

### 单独使用并不够
+ 需要严格本体与逻辑推理的知识图谱；
+ 需要实时一致性与自动冲突消解的知识系统；
+ 需要细粒度访问控制和密码学信任的场景；
+ 需要完整可信计算运行时与跨环境沙箱的场景。

## 十一、综合判断
OKF 最合理的定位是：

> Agent 时代的 Markdown-based metadata interchange format。
>

它的三个突出优点是：

1. **门槛低**：人、脚本和 Agent 都能直接读写；
2. **Git-native**：Review、Diff、回滚与归因可以复用软件工程流程；
3. **信任信息一等化**：来源、验证人、时效性和计算证明不再只是正文中的松散描述。

它的主要局限是：类型和关系缺少统一语义，身份仍是自声明，检索与权限不在规范内，Attestation 运行时尚未完整标准化。

因此，OKF 不适合被期待成“包办一切的知识平台”。它真正有价值的地方，是提供一个足够简单、可移植、可审查的知识内容层，让人、Agent 和现有工具围绕同一份知识制品协作。

## 参考资料
+ [Open Knowledge Format v0.2 Specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
+ [OKF 项目 README 与示例 Bundle](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/README.md)
+ [GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog)

> 说明：该仓库位于 GoogleCloudPlatform GitHub 组织下，但仓库 README 明确声明其中内容并非 Google 官方产品。当前规范版本为 v0.2，适合评估、试点和构建适配层，正式推广时仍应配套企业级校验与治理规则。
>

