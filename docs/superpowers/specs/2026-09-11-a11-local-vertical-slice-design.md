# A11 本地真实解析与规则审核纵向切片设计 v0.1

更新时间：2026-09-11  
状态：[你说的] 后续采用推荐方案连续推进，无需逐节确认  
上游基线：`docs/superpowers/specs/2026-09-10-a11-rule-baseline-and-validation-design.md`  
对应原型：`prototype/a11-ui/`

## 1. 决策摘要

- [你说的] 本阶段交付可在开发机本地运行的端到端版本：真实上传、真实解析、A11 客观规则执行、可追溯证据和现有审核页面联通。
- [你说的] 开发数据库使用 SQLite；正式生产数据库暂不确定。
- [你说的] 当前 17 个样本全部用于解析兼容验证，样本只读且不得修改内容或时间戳。
- [你说的] 当前开发与验收机器保证安装 Microsoft Word，并允许系统只读打开或转换旧版 `.doc`。
- [你说的] 本阶段不调用大语言模型；需要语义判断且没有客观确定结论的项目进入“待人工确认”。
- [你说的] 客观硬性问题或必需证据缺失优先形成“不符合”，不得因语义部分尚未审核而降为“待人工确认”。
- [你说的] 临时解析文件按任务隔离，任务完成或失败后立即清理；异常残留最迟在 24 小时内删除。
- [你说的] 单文件“解析＋客观规则执行”超过 20 分钟即判性能验收失败；同时记录 17 个样本的解析耗时、规则耗时和峰值内存。
- [我推断的] 采用“格式专用解析器 → 统一报告模型 → A11 规则引擎”的结构化解析路线；Microsoft Word 仅作为旧版 DOC 的受控转换依赖。

## 2. 本阶段目标与非目标

### 2.1 目标

1. 对样本目录中的 12 个 XLS、2 个 DOC、3 个 PDF 共 17 个文件实现 100% 可诊断读取；失败时必须输出文件、处理阶段和错误原因。
2. 每个文件形成统一的结构化解析快照，至少包含文本、表格、工作表或页、图片/附件位置以及稳定证据地址。
3. 对每个独立报告任务生成 A11 的 21 个执行项初判；TR-05 只保留源行和证据地址语义，不参与执行。
4. 规则结果只允许“符合、不符合、不适用、待人工确认”四种系统初判，并为每一项保留判定依据或无法判定原因。
5. 将真实任务、解析进度、规则结果和人工改判接入现有审核界面；刷新或重启后可从 SQLite 恢复。
6. 证明解析过程不会修改原始样本的内容、大小、哈希和最后修改时间。

### 2.2 非目标

- [你说的] 不接入真实大语言模型 API。
- [你说的] 不生成或写回正式 XLS 审核副本。
- [我推断的] 不实现登录、多人并发、网络部署、组织权限或生产级备份恢复。
- [我推断的] 不实现模板上传、版本发布和规则在线编辑的真实后端；继续使用冻结的 A11 规则基线。
- [我推断的] 不把历史已填写检查表当作准确率金标准。
- [我推断的] 未提供真实 DOCX/XLSX 样本前，不宣称这两种格式通过兼容验收。

## 3. 总体架构

```text
浏览器中的现有审核界面
        │
FastAPI 任务/API 层
        │
        ├── 任务与生命周期服务
        ├── 解析调度服务
        ├── A11 审核服务
        └── 人工复核与修订服务
        │
格式适配器边界
        ├── XLS 结构解析器
        ├── DOC 受控转换与结构解析器
        └── PDF 结构解析器
        │
统一报告模型与证据定位器
        │
确定性 A11 规则引擎
        │
SQLite 元数据/结果与任务级文件存储
```

### 3.1 Component responsibilities

| 组件 | 职责 | 明确不负责 |
|---|---|---|
| 前端 | 上传材料、显示阶段进度、结果证据、人工改判、完成与重开 | 不解析文件，不自行计算状态 |
| API 层 | 输入校验、响应模型、错误码、调用应用服务 | 不包含格式解析细节 |
| 任务服务 | 任务状态机、幂等执行、失败记录、修订版本 | 不判断 A11 业务语义 |
| 格式适配器 | 将一种源格式转换为统一报告模型 | 不输出审核结论 |
| 规则引擎 | 执行冻结的 A11 原子规则、汇总系统初判、生成证据 | 不访问 UI，不直接执行 SQL |
| 仓储接口 | 持久化任务、产物、结果、人工决定和修订版 | 不存放源文件二进制 |
| 任务文件存储 | 存放只读副本和临时转换产物，执行生命周期清理 | 不作为审计状态的唯一来源 |

### 3.2 任务状态机

`CREATED → FILES_STAGED → PARSING → PARSED → EVALUATING → READY_FOR_REVIEW → COMPLETED`

- `PARSING` 或 `EVALUATING` 失败时进入 `FAILED`，记录 `stage`、稳定错误码、可读原因和发生时间。
- 对同一任务重复触发执行必须幂等：已完成阶段不得重复插入结果或修订版。
- `FAILED` 可从明确的失败阶段重试；重试沿用源文件哈希，不覆盖先前失败诊断。
- `COMPLETED` 后修改结果必须先重新打开，形成下一审核修订版。

## 4. 统一报告模型与证据定位

### 4.1 核心实体

| 实体 | 关键字段 |
|---|---|
| `SourceFile` | `id`, `task_id`, `role`, `evidence_kinds`, `original_name`, `detected_format`, `size_bytes`, `sha256`, `mtime_before`, `parser_version` |
| `ReportDocument` | `id`, `source_file_id`, `format`, `container_count`, `text_digest`, `parse_warnings` |
| `DocumentContainer` | `id`, `kind` (`sheet`/`page`), `name_or_number`, `order` |
| `ContentBlock` | `id`, `container_id`, `kind` (`text`/`table`/`image`/`attachment`), `order`, `text`, `bbox`, `content_hash` |
| `TableCell` | `block_id`, `row`, `column`, `address`, `raw_value`, `display_value`, `formula_if_available`, `merged_range` |
| `EvidenceLocator` | `source_file_id`, `container`, `structural_address`, `bbox`, `quoted_text`, `content_hash` |
| `RuleResult` | `task_id`, `rule_id`, `initial_status`, `basis`, `missing_materials`, `evidence_locators`, `engine_version` |
| `ManualDecision` | `rule_result_id`, `final_status`, `reason`, `supplemental_evidence`, `actor`, `decided_at` |
| `ReviewRevision` | `task_id`, `revision_no`, `completed_at`, `result_snapshot` |

`role` 仅允许 `PRIMARY_REPORT` 或 `SUPPORTING_EVIDENCE`。支撑材料必须由用户选择一个或多个 `evidence_kinds`，可选值为：`JIRA_RECORD`、`PREVIOUS_STAGE_REPORT`、`POWER_RECORD`、`REQUIREMENT_OR_CASE_MAPPING`、`PAPER_RECORD`、`EMC_REPORT`、`TEMPERATURE_RECORD`、`AUTOMATION_RECORD`、`PUBLISHED_CRITERIA`、`OTHER`。标签只用于把材料路由给相关规则，不能代替内容校验。源文件扩展名不能单独决定格式，必须同时记录文件签名检测结果；扩展名和签名冲突时拒绝解析并给出明确错误。

### 4.2 证据地址规则

- XLS：`文件哈希 + 工作表名称/序号 + 单元格或区域 + 引用值哈希`；合并单元格记录主单元格与合并范围。
- DOC：`原文件哈希 + 转换产物哈希 + 页码 + 段落/表格地址 + 引用文本哈希`；页码用于展示，结构地址用于稳定追踪。
- PDF：`文件哈希 + 页码 + 文本块/表格块 + 边界框 + 引用文本哈希`。
- 图片或附件无可提取文字时，证据地址仍记录所在容器、顺序、边界框、对象类型和内容哈希，不虚构图片内容。
- 每条“不符合”至少有一个证据定位或一个明确的缺失材料记录；“待人工确认”必须写出不能形成确定结论的具体原因。

## 5. 格式解析边界

### 5.1 通用预检

1. 将用户选择的文件复制到任务专属 `input/` 目录；解析器只读取副本。
2. 记录原文件与副本的大小、SHA-256 和最后修改时间；解析前后重新校验原文件元数据和 SHA-256。
3. 校验扩展名、文件签名、大小上限和可读性；禁止执行宏、外链程序、OLE 脚本和嵌入程序。
4. 解析器运行在可取消的工作进程中，并设置单文件超时；超时和崩溃必须转换为稳定的阶段错误。

### 5.2 XLS 适配器

- 读取工作表名称与顺序、已用区域、单元格原始值与显示值、可用的公式缓存值、合并单元格、行列位置和嵌入对象目录。
- 不重新计算公式；若源文件只包含公式且无缓存显示值，记录解析警告，不臆造结果。
- 本阶段只登记并定位图片和 OLE 对象；不执行 OCR，也不运行嵌入程序。

### 5.3 DOC 适配器

- 通过独立 Microsoft Word 工作进程，以只读、禁用宏、禁止更新外链的方式打开任务副本。
- 产出 PDF 视觉副本以及可遍历的文档结构；两者均位于任务临时目录。
- Word 无法打开或转换、出现阻塞对话框时返回 `DOC_CONVERSION_FAILED`；工作进程必须超时退出，不能阻塞主服务。
- 证据定位关联原文件哈希、转换产物哈希、页码和结构地址；任何中间产物都不能替代原文档身份。

### 5.4 PDF 适配器

- 提取页、文本块、表格候选、图片目录和坐标。
- 无文本层或扫描页记录为 `IMAGE_ONLY_PAGE`；本阶段不实现 OCR，不能根据未读取的内容将相关规则判为符合。
- 加密、损坏或不支持的 PDF 返回稳定错误，不产生局部“符合”结果。

## 6. A11 规则执行语义

### 6.1 原子结果

每个原子检查返回：

```text
status: COMPLIANT | NON_COMPLIANT | NOT_APPLICABLE | NEEDS_REVIEW
basis_code: stable rule reason code
basis_text: human-readable reason
evidence: EvidenceLocator[]
missing_materials: string[]
unresolved_semantics: string[]
```

### 6.2 经确认的判定优先级

本阶段采用以下优先级，替代旧的“任一原子项待确认则整项待确认”：

1. 有完整证据证明不适用 → `NOT_APPLICABLE`。
2. 任一必需外部证据缺失 → `NON_COMPLIANT`。
3. 任一客观硬性检查有明确失败证据 → `NON_COMPLIANT`。
4. 没有硬性失败，但因未接入大模型而无法判断语义关系 → `NEEDS_REVIEW`。
5. 所有适用的客观和语义要求均有证据证明通过 → `COMPLIANT`。

由于本阶段不运行大模型，纯 AI 规则通常进入 `NEEDS_REVIEW`；如果必需证据缺失，则按第 2 条明确判为 `NON_COMPLIANT`。“规则+AI”项目先执行客观子项，只有不存在确定性硬性失败时，未解决的语义部分才使整项进入 `NEEDS_REVIEW`。

### 6.3 规则实现边界

- 22 个源行持续可见，只有 21 项可执行；TR-05 不能生成 `RuleResult`。
- 每条规则由小型原子检查组成；源行汇总器只负责按优先级汇总状态和合并证据。
- 每个任务结果冻结规则定义和引擎版本，后续代码变化不得静默改写历史结果。
- 不得编造未知的映射、命名规则、首页字段、排序依据或喷漆期望；必须按已确认的缺失材料或未解决语义处理。
- 人工可将任一系统初判改为符合、不符合或不适用；修改原因必填，补充证据选填，并保留系统初判。

## 7. API and persistence design

### 7.1 推荐接口

| 方法/路径 | 用途 | 可观测结果 |
|---|---|---|
| `POST /api/tasks` | Create a task and upload a primary report/supporting materials | Returns task ID, file manifests and `CREATED` state |
| `POST /api/tasks/{id}/execute` | Idempotently run stage/parse/rules | Returns `202`; polling state progresses or fails with stage diagnosis |
| `GET /api/tasks` | List recent real tasks | Totals and statuses from SQLite |
| `GET /api/tasks/{id}` | Get task, files, stage diagnostics, 21 results and revisions | Frontend's sole task-detail source |
| `PUT /api/tasks/{id}/rules/{rule_id}/manual-decision` | Save or replace the current revision's manual decision | Rejects disabled TR-05, invalid final states, blank reasons and completed tasks |
| `POST /api/tasks/{id}/complete` | Complete when no unresolved `NEEDS_REVIEW` remains | Creates an independent revision snapshot |
| `POST /api/tasks/{id}/reopen` | Open the next revision | Preserves all previous snapshots |

任务创建只接受一个 `PRIMARY_REPORT`；支撑文件可选，但每个文件必须具有明确的 `evidence_kinds`。请求与错误响应使用稳定字段名和错误码。

### 7.2 SQLite 边界

- 使用迁移脚本管理数据库结构，不在运行时临时建表。
- 时间戳以 UTC 保存并按 ISO 8601 返回；界面显示本地时间。
- 为“任务＋规则＋活动修订版”和“任务＋修订号”设置外键及唯一约束。
- 任务状态变化、21 项结果整体替换和修订快照创建各自处于明确事务边界内。
- 业务服务依赖仓储接口，不依赖 SQLite 专属 SQL；生产数据库保持 [待确认]。
- 源文件和中间文件不以 BLOB 形式存入数据库。

## 8. Frontend integration

- Preserve the currently approved information architecture, names, state colors and role demonstration.
- 将演示任务创建替换为多文件上传和真实 API 响应；支撑材料上传时要求选择一个或多个证据类型标签。仅为静态原型回归测试保留显式演示模式。
- Show stage progress and stable failures: filename, stage, reason and retry action.
- Render evidence locators by format: XLS sheet/cell, DOC page/paragraph/table, PDF page/area.
- Keep comparison of system initial state and manual final state; do not merge system evidence with manual reason.
- Template management screens stay simulated and clearly labeled as not connected to a real backend.
- The role selector remains a demonstration permission switch; it is not presented as real authentication or authorization.

## 9. Security, cleanup and failure behavior

- 服务默认只监听 `127.0.0.1`；是否允许外部网络访问必须另行确认。
- 文件名仅作为展示元数据，不能决定磁盘路径；实际文件使用系统生成的 ID 存放。
- 解析过程不跟随外链，不执行宏、嵌入应用或脚本。
- 任务工作目录创建在配置的窄范围根目录下，清理前必须验证目标路径；禁止对宽泛或未解析的路径执行递归删除。
- 任务完成或失败时，在持久化事实和结果后立即清理；启动清理器删除超过 24 小时的任务级残留。
- 解析失败不能转换成 `COMPLIANT`；已成功提取的局部结构只能作为诊断保留，不进入完整规则结论。

## 10. Test and acceptance design

### 10.1 Automated layers

1. **Domain unit tests:** state priority, TR-05 exclusion, required reason, revision immutability and file-role validation.
2. **Parser contract tests:** all adapters produce the same normalized interfaces and stable evidence locators.
3. **Rule tests:** each A11 rule covers compliant, noncompliant, not-applicable when valid, missing-material and unresolved-semantic branches.
4. **Repository/API tests:** migrations, restart recovery, idempotent execution, stage failure and revision snapshots.
5. **Browser tests:** real upload, progress, evidence display, override, pending gate, completion and reopen.
6. **Readonly sample acceptance:** record original hash/size/mtime, parse 17 files, rerun checks, and produce a machine-readable results matrix.

### 10.2 Stage acceptance gates

| Gate | Passing condition |
|---|---|
| G1 Source protection | 17/17 files have identical SHA-256, size and mtime before/after |
| G2 Readability | 17/17 produce a normalized document or a diagnosed failure; because the stated target is 100% reading success, any diagnosed failure keeps the stage NO-GO until fixed |
| G3 Structural completeness | Every document has container inventory; readable text/tables are extracted; image/attachment locations are inventoried |
| G4 Rule completeness | Each of 15 independent report tasks produces exactly 21 `RuleResult` records and no TR-05 result |
| G5 Traceability | Every noncompliant result has evidence or missing-material record; every pending result has an unresolved reason |
| G6 Lifecycle | SQLite-backed task survives service restart; manual override, completion, reopen and two independent snapshots pass |
| G7 Performance | Each file parse + objective-rule execution ≤20 minutes; report per-file parse time, rule time and peak memory |
| G8 UI | Current browser flow runs against real API without losing the approved state and role boundaries |

Historical completed A10/A11 sheets are not expected outputs. Acceptance checks structural extraction, rule determinism and evidence traceability; human reviewers provide qualitative spot checks but are not encoded as a fabricated accuracy dataset.

## 11. Deferred decisions and upgrade path

| Deferred item | Current default | What it blocks |
|---|---|---|
| Production database | SQLite only in development; PostgreSQL is the recommendation but not frozen | Multi-user production deployment |
| Production file/object storage | Task-scoped local filesystem | Central deployment and retention policy |
| LLM provider, model and data policy | No external call | Semantic automatic decisions |
| DOCX/XLSX compatibility | API labels may remain visible, but no compatibility claim | Format acceptance for these two extensions |
| OCR | Image-only pages produce diagnostics/pending or missing-evidence outcomes | Automatic reading of scanned content |
| Authentication and RBAC | Local demonstration roles only | Production authorization acceptance |
| Formal XLS writer and Office/WPS verification | Export remains out of scope | Production review-copy delivery |

## 12. Traceability to confirmed needs

| Confirmed need | Design response |
|---|---|
| Rules first, semantic decisions later | Sections 5–6 adapter/engine separation and priority |
| Hard missing evidence is noncompliant | Section 6.2 priority item 2 |
| Human decision is final | Sections 6.3 and 7.1 manual-decision endpoint |
| Every problem has traceable evidence | Sections 4.2 and gate G5 |
| Do not modify the report or source template | Sections 5.1, 9 and gate G1 |
| 22 source rows / 21 executed checks | Sections 6.3 and gate G4 |
| 17 compatibility files / 15 report tasks | Section 10.2 gates G1–G4 |
| Reduce review time toward 20 minutes | Gate G7 measures the automated part without misrepresenting end-to-end completion |

This design answers what the first real local vertical slice builds, how formats become evidence-bearing data, how objective results are determined, and what proof is required before the phase can pass.
