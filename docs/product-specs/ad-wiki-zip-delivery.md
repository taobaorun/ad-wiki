# Product Contract: Deterministic ZIP Skill Delivery

Authority: 用户于 2026-08-24 明确要求现有 `ad-wiki-ship` 支持 ZIP 压缩构建产物，并紧接着调用 `ad-gallop` 接受完整自主交付。用户调用前已确认的方案是：保留 `directory` 默认行为，新增 `zip` 与 `both`；ZIP 是同一个 `ad-${wiki-name}` Skill 目录的确定性传输格式，而不是另一套知识产物。

Product Context: not-available；这是对已发布 `ad-wiki-ship` 交付界面的独立增量任务，不重写 `docs/product-specs/ad-wiki-skill-delivery.md`。

## Actor and observable outcome

AD Wiki 构建者可以在交付一个已完成 Wiki 时选择目录、ZIP，或同时生成二者。ZIP 下载、复制或上传后，解压即得到与目录模式内容完全一致、可直接安装的 `ad-${wiki-name}/` Skill；相同输入与选项重复构建得到字节一致的 ZIP。

## Requirements

- R-ZD1 — 构建接口必须支持 `directory | zip | both` 三种格式；acceptance: CLI 和 Python API 对三种值分别成功，其他值以结构化错误拒绝；owner/method: engineering，API/CLI parameter tests；provenance: 用户要求 ZIP，已确认三模式方案。
- R-ZD2 — `directory` 必须继续作为默认格式并保持 `1.7.0` 的目录行为和结果兼容；acceptance: 未传格式时输出路径、目录内容、artifact digest、重复构建和冲突语义与现有测试一致；owner/method: engineering，compatibility regression tests；provenance: 已确认“默认仍为 directory，避免破坏现有调用方”。
- R-ZD3 — `zip` 模式只发布 `<output-parent>/ad-${wiki-name}.zip`，不留下最终目录；acceptance: 成功后 ZIP 存在而同名 Skill 目录不存在，构建临时目录已清理；owner/method: engineering，filesystem journey；provenance: 已确认三模式语义。
- R-ZD4 — `both` 模式发布同级的 `ad-${wiki-name}/` 与 `ad-${wiki-name}.zip`；acceptance: 二者均存在且解压内容逐文件、权限语义和 manifest 身份一致；owner/method: engineering，dual-output comparison；provenance: 已确认三模式语义。
- R-ZD5 — ZIP 必须包含唯一顶层目录 `ad-${wiki-name}/`，解压后可直接作为 Skill；acceptance: archive entry 集合无顶层散文件、绝对路径、`..`、反斜杠或额外根，并通过生成 Skill validator；owner/method: engineering/security，ZIP entry inspection + validator；provenance: 已确认 ZIP 布局。
- R-ZD6 — ZIP 必须是确定性传输表示；acceptance: 相同 Wiki、名称、模板版本和格式选项在不同输出父目录、不同构建时间下生成字节一致的 ZIP；entry 顺序、时间戳、权限、host metadata、压缩方法/级别、额外字段和注释均不引入波动；owner/method: engineering，byte-for-byte reproducibility tests；provenance: 已确认“固定时间戳、权限与压缩参数”。
- R-ZD7 — `artifact_digest` 和包内 Artifact Manifest 继续表示解压后的 Skill 内容身份，不因传输格式改变；ZIP 自身以独立 `archive_sha256`、字节数和路径报告，不把自身 digest 写入包内造成自引用；acceptance: 三模式 artifact/manifest digest 一致，ZIP SHA 可从输出文件独立重算；owner/method: engineering，cross-format digest tests；provenance: 已确认双重身份方案。
- R-ZD8 — ZIP 内容必须严格等于已验证目录候选；acceptance: 完整 Bundle、Source Registry、登记 Raw 和只读 Query/helper 全部保留，runs/cache/lock、未登记 Raw、外部代码仓库和本机路径仍不进入；owner/method: engineering/security，entry allowlist and real SOFA inspection；provenance: 既有交付合同和用户要求 ZIP 只是格式扩展。
- R-ZD9 — 每个目标必须保持不可变和无覆盖；acceptance: 已存在的字节相同目录/ZIP返回 `unchanged`，任一非相同目标使构建在发布前失败且不改动该目标；owner/method: engineering，identical/conflict tests；provenance: 既有 immutable delivery contract。
- R-ZD10 — `both` 的发布必须保持事务完整性；acceptance: 发布前校验两个目标，故障注入证明不会留下本次新建的单边目录或 ZIP，也不会删除调用前已存在的相同产物；owner/method: engineering，fault-injection and recovery tests；provenance: 已确认原子构建原则，engineering delegated default for multi-target recovery。
- R-ZD11 — 构建结果必须清楚区分内容与传输产物；acceptance: JSON/普通语言报告包含请求格式、聚合状态、主输出、目录状态/路径（如有）、ZIP 状态/路径/SHA/size（如有）、既有能力和警告；owner/method: engineering/product，CLI contract tests；provenance: 已确认 archive digest 输出和既有 R-SD17。
- R-ZD12 — ZIP 构建保持本地、只读和宿主中立；acceptance: 不联网、不部署、不安装、不上传、不写源 Wiki，不引入第三方运行依赖，使用 Python 标准库即可构建和读取 ZIP；owner/method: engineering/security，dependency/static/source byte checks；provenance: 既有交付边界。
- R-ZD13 — 此能力作为向后兼容的 Plugin `1.8.0` minor 发布；acceptance: 双宿主 manifest、Runtime、模板版本引用和 packaging tests 使用 `1.8.0`，Profile `0.1`、OKF `0.2`、Source Registry v1 和 delivery template v1 不迁移；owner/method: engineering，release identity/package tests；provenance: 用户接受的 minor 版本方案。

## In scope

- `ad-wiki-ship` Python/CLI 格式选项；
- ZIP-only、directory-only、both 输出；
- 确定性 ZIP entry metadata、排序、压缩与顶层目录；
- ZIP SHA/size/result contract；
- 冲突、相同产物、双输出恢复与故障注入；
- 真实 `sofa-wiki` ZIP 构建、解压 Skill 校验和版本 `1.8.0`。

## Out of scope

- tar、tar.gz、7z、分卷压缩、加密 ZIP、密码、签名或远程制品仓库；
- 自动上传 GitHub Release、Marketplace、服务器、对象存储、镜像或部署系统；
- 自动安装或解压到 Agent 的全局 Skill 目录；
- 多 Wiki 聚合 ZIP、增量 ZIP 或 archive 内 writeback；
- 修改 Wiki 内容、Source Registry、Raw、runs 或 Code Wiki。

## Constraints and confirmed decisions

- ZIP 是目录 Skill 的传输表示，包内 manifest 和 artifact digest 不因格式改变。
- ZIP 时间戳使用 ZIP 可表达的固定 epoch，entry 使用 POSIX 风格路径和规范化权限；不复制构建机 UID/GID、绝对路径或扩展属性。
- `zip` 模式不要求保留可见目录，但实现可以在私有临时目录中复用完整目录候选。
- `both` 发生中途发布故障时，只回滚本次新建的输出，绝不删除调用前已经存在的相同目录或 ZIP。
- ZIP 压缩算法和级别由工程固定为标准库跨平台可重复的单一组合，并由测试锁定。

## Delegated engineering defaults and boundaries

- Engineering 可决定 Python API 参数名、JSON 中新增字段的精确嵌套、固定 ZIP 时间戳、压缩级别及内部 staging/rollback 机制，但必须满足三模式、默认兼容、字节可复现和无覆盖。
- Engineering 可复用当前目录候选、manifest 和 tree-identity 实现；不得为 ZIP 另建一套知识选择、模板或安全门禁。
- Engineering 可在 `both` 中以可恢复的顺序发布两个目标，但不得把普通失败伪装成成功或留下本次新增的半套产物。

## Open product decisions

无。
