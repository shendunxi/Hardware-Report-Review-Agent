# Hardware-Report-Review-Agent

> 硬件测试报告审核智能体 —— 用 A11《硬件测试过程检查表》对硬件测试报告做**可追溯、可复现**的自动审核。

[![Release](https://img.shields.io/badge/release-NO--GO-red)](#-当前状态与能力边界)
[![Backend](https://img.shields.io/badge/backend-Python%203.12%2B-blue)]()
[![Frontend](https://img.shields.io/badge/frontend-Vue%203%20%2B%20Vite%207-42b883)]()

---

## 目录

- [解决什么问题](#-解决什么问题)
- [当前状态与能力边界](#-当前状态与能力边界)
- [核心设计原则](#-核心设计原则)
- [技术栈](#-技术栈)
- [目录结构](#-目录结构)
- [快速开始](#-快速开始)
- [使用流程](#-使用流程)
- [API 概览](#-api-概览)
- [测试与验收](#-测试与验收)
- [配置](#-配置)
- [文档索引](#-文档索引)
- [开发约定](#-开发约定)

---

## 解决什么问题

硬件测试报告目前完全依赖人工逐项核对：

| 现状 | 量化 |
|---|---|
| 单份审核耗时 | 约 **4 小时** |
| 年审核量 | **1000+ 份** |
| 现有错误率 | 约 **10%** |
| 主要痛点 | 模板不规范、结论与数据不一致、关键附件/截图缺失、测试项遗漏、版本信息不完整、**结论缺少可复现的定位依据** |

本系统的目标是把「客观可判定的部分」交给机器，把「需要语义判断的部分」明确地交还给人工，并且**每一条结论都留下可复现的证据地址**。

**目标指标**：P95 单份审核 ≤ 20 分钟 · 自动判定覆盖率 ≥ 90% · 待人工确认占比 ≤ 10% · 不符合项依据覆盖率 100%

### 明确的非目标

- 不修改、覆盖或回写**原报告**与**源模板**
- 不提供「无法判断」或「接受例外」结果状态
- 不设置问题严重性或风险等级
- **不以历史已填写的 A10/A11 检查表作为正确答案或训练金标准**
- 不直接连接 JIRA 或共享目录，只接收任务随附的导出件、截图或文件
- 不执行上传文件中的宏、外链程序或嵌入程序

---

## 当前状态与能力边界

> **整体发布决策：NO-GO**（不代表系统不可用，而是「尚未完成真实样本全格式覆盖」）

依据 [`docs/evidence/a11-local-vertical-slice/release-gates.md`](docs/evidence/a11-local-vertical-slice/release-gates.md)：

| 门禁 | 决策 | 说明 |
|---|---|---|
| G1 源文件保护 | **GO** | 17/17 指纹未变化，全程只读 |
| G2 可读性 | **NO-GO** | 15/17 解析成功（DOCX/XLSX 缺真实样本验收证据） |
| G3 结构完整性 | **NO-GO** | 依赖 G2 |
| G4 规则完整性 | **GO** | 15/15 任务组均产出 21 项结果 |
| G5 可追溯性 | **GO** | 每个不符合项有证据或缺失材料；每个待确认项有未决原因 |
| G6 生命周期 | **GO** | 后端 303 passed / 8 skipped，前端 51 passed |
| G7 性能 | **GO** | 单文件解析 + 规则判定均 ≤ 1200 秒 |
| G8 界面 | **GO** | 真实浏览器流程 + 1440×900 / 1280×720 / 760×900 |

**已单独 GO 的子切片**（不改变整体 NO-GO）：A11 已填检查表导出、持久化模板管理、动态任务模板绑定。

**尚未实现或未验证**：

- ⚠️ **生产身份认证** —— 角色已由签名 Cookie + 服务端路由权限强制执行，但**企业微信 / OIDC / LDAP / SSO 尚未接入**，本地会话仅限回环地址，生产认证门禁仍为 **NO-GO**
- ❌ 真实大模型调用、OCR
- ❌ 生产数据库选型（当前仅 SQLite）
- ⚠️ DOC 解析默认只接受**真实 Microsoft Word**。仅有 WPS 的主机需显式设置 `HW_REVIEW_WORD_AUTOMATION_POLICY=any_word_compatible` 才能转换，且该通道**不是验收级证据**（见「配置」）

---

## 核心设计原则

只要记住一句话：**能确定的就用客观规则判，不能确定的绝不猜，一律挂 `NEEDS_REVIEW` 交给人工，且每条结论必须留下可复现的证据地址。**

| 原则 | 落地方式 |
|---|---|
| **不臆造标准** | 未提供命名规则、必填字段清单、排序依据、喷漆期望等外部标准时，系统输出「未提供标准，不会自行推断」，而不是猜一个 |
| **证据可追溯** | 每条结论携带 `EvidenceLocator`（文件、工作表/页、A1 地址或块地址、原文引用、内容哈希） |
| **源文件只读** | 上传后立即复制到 UUID 隔离工作区并做「签名 + 尺寸 + 指纹」三重校验；导出生成**新文件**，源模板 SHA-256 校验后才使用 |
| **确定性可复现** | 结果 ID 由 `uuid5(task, revision, rule, engine, baseline)` 派生；快照 JSON 使用 `sort_keys` 紧凑序列化，可逐字节比对 |
| **不可变审计** | 完成审核后快照冻结，人工判定被 `revision_id` 锁定；重开产生新修订版，历史不可篡改 |
| **人工优先级** | 导出时人工最终判定覆盖系统初判；未改判项隐式接受系统结论 |

### A11 规则集

- **22 个源行**（TR-01 ~ TR-22），其中 **21 个执行项**
- `TR-05`（共享路径）为 `DISABLED` —— 作为 TR-04 的证据地址保留源行，不计入执行项
- 每条规则的 `main_judgment` 标记判定方式：`RULE`（纯客观）/ `RULE_PLUS_AI` / `AI`（语义）/ `DISABLED`
- **未配置自动实现的规则一律产出 `NEEDS_REVIEW`**，绝不降级为「符合」

### 判定状态

| 系统初判 `ReviewStatus` | 人工最终判定 `FinalStatus` |
|---|---|
| `COMPLIANT` 符合 | `COMPLIANT` ✅ |
| `NON_COMPLIANT` 不符合 | `NON_COMPLIANT` ✅ |
| `NOT_APPLICABLE` 不适用 | `NOT_APPLICABLE` ✅ |
| `NEEDS_REVIEW` 待人工确认 | ❌ 不可作为最终状态，必须改判 |

### 任务状态机

```
CREATED → FILES_STAGED → PARSING → PARSED → EVALUATING → READY_FOR_REVIEW → COMPLETED
                                                                  ↑               │
                                                                  └── reopen ─────┘
           任意阶段异常 ──────────────────────────────→ FAILED（需重新上传）
```

---

## 技术栈

| 层 | 选型 |
|---|---|
| 后端语言 | **Python ≥ 3.12**（`pywin32` 决定完整链路仅 Windows 可跑） |
| Web 框架 | **FastAPI** + **Uvicorn**（应用工厂 `create_app`） |
| 数据契约 | **Pydantic v2**：全量 `frozen=True` 不可变模型 + 模型内不变式校验 |
| 持久化 | **SQLAlchemy 2 Core**（非 ORM）+ **Alembic** + **SQLite** |
| 文档解析 | `xlrd` / `openpyxl` / `xlutils`（XLS/XLSX）· `olefile`（OLE 探测）· `pymupdf`（PDF）· `pywin32` + `psutil`（Word 隔离子进程） |
| 前端 | **Vue 3.5** + **TypeScript 5.9** + **Vite 7** + **Vue Router 4.5** + **Pinia 3** |
| 前端测试 | **Vitest 3** + happy-dom + `@vue/test-utils` + `@testing-library/vue` |
| 包管理 | 后端 `pip` · 前端 **`pnpm`** |

---

## 目录结构

```
.
├── backend/                        # Python 后端
│   ├── src/hw_review/
│   │   ├── domain/                 # 纯领域层：枚举、不可变模型、端口协议、哈希
│   │   ├── parsers/                # XLS / XLSX / DOC / DOCX / PDF + Word 隔离子进程
│   │   ├── rules/                  # A11 注册表（22 源行）+ 判定引擎（21 项实现）
│   │   ├── services/               # 生命周期、暂存、评估、模板、导出、清理
│   │   ├── persistence/            # SQLAlchemy Core 表结构 + 仓储实现
│   │   ├── api/                    # FastAPI 装配、错误映射、路由
│   │   └── acceptance/             # 17 份真实样本验收 runner
│   ├── tests/                      # unit / integration / acceptance 三层
│   ├── migrations/versions/        # Alembic 迁移（0001~0003）
│   ├── resources/a11/              # A11 基线模板 .xls（必须入库）
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/                       # Vue 3 正式前端
│   ├── src/api/                    # REST 客户端（统一 ApiError）
│   ├── src/domain/                 # 类型定义 + 审核行派生逻辑
│   ├── src/stores/                 # Pinia：session / tasks / templates
│   ├── src/views/                  # 8 个页面视图
│   ├── src/components/             # AppShell / ReviewResultCard / StatusBadge / ErrorPanel
│   └── vite.config.ts              # /api → 127.0.0.1:8766 代理
├── prototype/a11-ui/               # 旧原生 JS 原型（回归基线 + 构建缺失时兜底）
├── docs/
│   ├── requirements/               # PRD、字段字典、规则清单、样本目录
│   ├── superpowers/specs|plans/    # 每个切片的确认设计与实施计划
│   └── evidence/                   # 门禁与验收证据
└── .gitignore
```

---

## 快速开始

### 环境要求

| 依赖 | 版本 / 说明 |
|---|---|
| Python | **≥ 3.12** |
| Node.js | 建议 ≥ 20，需 **pnpm**（`npm i -g pnpm`） |
| 操作系统 | **Windows**（`pywin32`） |
| Microsoft Word | 解析 `.doc` / `.docx` 的**默认**宿主。仅有 WPS 时须设 `HW_REVIEW_WORD_AUTOMATION_POLICY=any_word_compatible`（开发通道，非验收级） |
| SQLite | Python 内置，无需单独安装 |

### 后端

```powershell
cd backend

# 1) 安装依赖（推荐虚拟环境）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"

# 2) 初始化数据库
python -m alembic upgrade head

# 3) 启动服务（务必在 backend 目录下运行：配置使用相对路径）
python -m uvicorn hw_review.api.app:create_app --factory --host 127.0.0.1 --port 8766
```

打开 <http://127.0.0.1:8766/> 即可访问。

> **注意**：`pyproject.toml` 未声明 `[build-system]`。若 `pip install -e .` 在你的环境不生效，可改用
> `$env:PYTHONPATH="src"` 后再运行 `python -m uvicorn ...`（pytest 已通过 `pythonpath=["src"]` 兜住）。

### 前端

```powershell
cd frontend
pnpm install
pnpm dev          # http://127.0.0.1:5173，/api 自动代理到 8766
```

生产构建（构建后由后端同源托管，仍走 8766 端口）：

```powershell
pnpm typecheck
pnpm build        # 产物 → frontend/dist/
```

> 后端在 `frontend/dist/index.html` 存在时托管 Vue 应用；**不存在时静默回退到 `prototype/a11-ui` 旧原型**。
> 若发现页面是旧版样式，先确认是否已完成 `pnpm build`。

### 首次启动会发生什么

`create_app()` 会调用 `TemplateService.ensure_baseline()`，把内置的 `resources/a11/hardware-test-process-checklist-a11.xls` 校验后注册为**已发布的 `A11` 基线模板**（幂等，重复启动不会重复插入）。若该文件缺失或结构不合法，服务启动即失败。

---

## 使用流程

系统有两个角色，权限取并集（同一账号可同时具备）。

### 流程 A · 测试报告审核

1. **创建任务** —— 选择已发布的模板版本 → 上传 1 份主报告（`.pdf` / `.doc` / `.docx` / `.xls` / `.xlsx`）+ 可选外部证据（需标注 `EvidenceKind`，如 JIRA 记录、功耗记录、EMC 报告…）
2. **自动执行** —— 后台按 `CREATED → … → READY_FOR_REVIEW` 推进；前端每 2 秒轮询，直到离开过渡态
3. **查看结果** —— 每项显示系统初判 + 可追溯证据 + 缺失材料 + 未决原因
4. **人工改判** —— 任一系统初判可改为符合 / 不符合 / 不适用，**修改原因必填**，补充证据可选
5. **完成审核** —— 所有 `NEEDS_REVIEW` 项处理完毕才能完成；未改动项隐式接受系统初判
6. **导出检查表** —— 下载由智能体填写的 **A11 XLS 副本**（新文件，源模板与源报告不受影响）
7. **重开** —— 如需再改，重开生成新修订版，历史快照保留

### 流程 B · 模板规则管理

1. **上传** —— 仅接受 `.xls`，系统做只读结构校验：工作表名唯一、A2 版本号匹配（拒绝历史笔误 `A111`）、D~G 结果列存在、22 个源行及 B 列序号逐行一致
2. **编辑草稿** —— 新增 / 修改 / 删除校验项，字段白名单受限；`enabled` 与 `main_judgment` 自动联动
3. **发布** —— 存在 `ERROR` 级结构问题时阻止发布；语义类规则只给出 `WARNING`
4. **停用** —— 已发布版本**不可修改任何字段**，只能整体停用（`PUBLISHED → RETIRED`）

> 任务在创建时就把模板的启用规则**整体快照**冻结进 `tasks.template_rules_snapshot`。
> 因此后续修改或发布新模板版本**不会影响已创建的任务**。

---

## API 概览

统一错误响应体：`{"error": {"code": "...", "message": "...", "details": {...}}}`

### 任务

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/tasks` | 创建任务（multipart：`primary_report`、`supporting_files[]`、`supporting_manifest`、`template_id`） |
| `POST` | `/api/tasks/{id}/execute` | 触发执行（202，幂等抢占） |
| `GET` | `/api/tasks` | 任务列表（含结果 / 判定 / 失败 / 修订摘要） |
| `GET` | `/api/tasks/{id}` | 任务详情（含冻结规则、证据、历史修订） |
| `PUT` | `/api/tasks/{id}/rules/{rule_id}/manual-decision` | 保存人工改判 |
| `POST` | `/api/tasks/{id}/complete` | 完成审核并冻结快照 |
| `POST` | `/api/tasks/{id}/reopen` | 重开为新修订版 |
| `GET` | `/api/tasks/{id}/export` | 下载已填写的 A11 XLS 副本 |

### 模板

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/templates` | 版本列表 |
| `POST` | `/api/templates` | 上传新版本（`source` / `name` / `version` / `actor`） |
| `GET` | `/api/templates/{id}` | 详情（模板 + 全部规则） |
| `POST` | `/api/templates/{id}/rules` | 新增规则 |
| `PUT` | `/api/templates/{id}/rules/{rule_id}` | 修改规则（仅草稿） |
| `DELETE` | `/api/templates/{id}/rules/{rule_id}` | 删除规则（仅草稿） |
| `POST` | `/api/templates/{id}/publish` | 发布 |
| `POST` | `/api/templates/{id}/retire` | 停用 |

### 常用错误码

| 码 | HTTP | 含义 |
|---|---|---|
| `TASK_NOT_FOUND` / `TEMPLATE_NOT_FOUND` | 404 | 对象不存在 |
| `INVALID_TASK_STATE` / `TEMPLATE_STATE_INVALID` | 409 | 状态不允许该操作 |
| `UNRESOLVED_REVIEW_ITEMS` | 409 | 仍有待人工确认项，无法完成 |
| `TEMPLATE_PUBLISH_BLOCKED` | 409 | 存在结构错误，无法发布 |
| `TEMPLATE_IMMUTABLE` | 409 | 已发布 / 已停用模板不可修改 |
| `INVALID_UPLOAD` / `STAGE_FAILURE` | 422 | 上传或执行阶段失败 |
| `INVALID_REASON` / `INVALID_STATUS` | 422 | 人工改判参数非法 |

---

## 测试与验收

### 后端

```powershell
cd backend

python -m pytest                    # 全部（unit + integration + acceptance）
python -m pytest tests/unit          # 领域契约、规则、导出、暂存、清理
python -m pytest tests/integration   # API、解析器、仓储、静态前端
```

### 前端

```powershell
cd frontend
pnpm test         # Vitest
pnpm typecheck    # vue-tsc --noEmit
```

### 真实样本验收（17 份报告）

```powershell
cd backend
$env:PYTHONPATH = "src"     # 或已完成 pip install -e .

python -m hw_review.acceptance.run_samples `
  --manifest tests/acceptance/sample_manifest.json `
  --sample-root "D:\Document\AI创新应用大赛\硬件测试报告及检查表" `
  --output ../docs/evidence/a11-local-vertical-slice
```

样本根也可以用环境变量供给，避免在命令行里写本机路径：

```powershell
$env:HW_REVIEW_SAMPLE_ROOT = "D:\Document\AI创新应用大赛\硬件测试报告及检查表"
```

两者皆缺时 runner 立即以非零码退出，不会静默产出一份依赖本机的结果。

该 runner 会逐份执行「暂存 → 解析 → 规则判定」，核对源文件指纹未变，并输出：

- `sample-results.json` —— 机器可读明细
- `sample-results.md` —— 文件矩阵 + 任务组矩阵 + 门禁表
- `release-gates.md` —— 8 项发布门禁结论

退出码：全部 GO 返回 `0`，否则返回 `1`。

> **前置条件**：样本根中必须存在 manifest 里那 17 个 `relative_path`。
> manifest 只保存**仓库安全的相对路径**，样本根由运行时供给，因此同一份 manifest 可在任意机器复用；
> 若样本没有挂载，会得到 `SOURCE_NOT_FOUND` —— 这是预期行为，不是缺陷。
> 若证据文件要入库，请传入相对或可移植的 `--sample-root`，避免把本机绝对路径写进 `docs/evidence/`。

---

## 配置

全部配置集中在 [`backend/src/hw_review/config.py`](backend/src/hw_review/config.py) 的 `Settings`。
每一项都可用 `HW_REVIEW_` 前缀的环境变量覆盖；`get_settings()` 读取环境变量，未设置时使用下表默认值。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `database_url` | `sqlite:///./hw-review.db` | 开发库。**相对路径**，依赖进程工作目录为 `backend/` |
| `storage_root` | `./storage` | 上传暂存、Word 转换产物、模板受管副本 |
| `a11_template_path` | `resources/a11/hardware-test-process-checklist-a11.xls` | A11 基线模板 |
| `auth_mode` | `local` | 仅接受 `local` / `disabled`，其他值启动即失败 |
| `local_session_secret` | `local-development-only-change-me` | 会话 Cookie 签名密钥，空值启动即失败 |
| `local_session_ttl_seconds` | `28800` | 会话有效期 |
| `local_session_cookie` | `hw_review_session` | Cookie 名 |
| `execution_lease_seconds` | `1800` | 执行租约，**必须大于最长单次评估**（DOC 转换超时上限 1200s） |
| `workspace_ttl_seconds` | `86400` | 任务工作区保留期 |
| `word_automation_policy` | `microsoft_only` | Word 自动化宿主信任策略，见下 |

### `HW_REVIEW_WORD_AUTOMATION_POLICY`

`.doc` / `.docx` 转换只驱动注册为 `Word.Application` 的 COM 服务器。本项决定是否信任非
`winword.exe` 的宿主（例如 WPS Office）：

| 取值 | 语义 |
|---|---|
| `microsoft_only`（默认） | **验收级**。注册表指向的服务器路径不含 `winword.exe` 时直接拒绝，抛 `DOC_CONVERSION_FAILED` |
| `any_word_compatible` | **开发通道**。放行 WPS 一类 Word 兼容宿主 |

非法取值会被 `WordWorker` 在启动时拒绝，不会静默降级。

> **为什么默认拒绝 WPS**：WPS 会上报与真实 Word 相同的 `Application.Version`（实测 `12.0`），
> 且部分产物可能与 Word 不同（实测同一份报告 PDF 体积差 24.4%）。因此
> `ConversionProvenance.automation_host` 会记录实际使用的宿主，使每条 DOC 证据都能追溯到转换器。
> 实测数据与结论见 [`docs/evidence/word-automation-policy/verification.md`](docs/evidence/word-automation-policy/verification.md)。

> 运行时数据（`hw-review.db`、`storage/`、`.task-work/`）已在 `.gitignore` 中排除，不会进入版本库。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [`docs/requirements/hardware-report-review-agent-prd-v0.1.md`](docs/requirements/hardware-report-review-agent-prd-v0.1.md) | **PRD**：背景、目标与非目标、角色权限、功能需求、验收标准 |
| [`docs/requirements/template-field-dictionary-v0.1.md`](docs/requirements/template-field-dictionary-v0.1.md) | 模板字段字典 |
| [`docs/requirements/template-check-rules-v0.1.md`](docs/requirements/template-check-rules-v0.1.md) | 22 条检查规则明细 |
| [`docs/requirements/a11-validation-sample-catalog-v0.1.md`](docs/requirements/a11-validation-sample-catalog-v0.1.md) | 17 份验证样本目录 |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | 各切片**已确认**的设计方案 |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | 各切片实施计划 |
| [`docs/evidence/`](docs/evidence/) | 门禁结论与验收证据 |
| [`frontend/README.md`](frontend/README.md) | 前端开发说明与当前边界 |
| [`prototype/a11-ui/README.md`](prototype/a11-ui/README.md) | 旧原型说明（回归基线） |

**建议的阅读顺序**：PRD `2.3 非目标` → `domain/enums.py`（词汇表）→ `domain/models.py`（数据形状）→ `rules/a11_registry.py`（22 条业务规则）→ `services/lifecycle.py`（状态机主线）→ `api/routes/tasks.py`（对外形状）→ `frontend/src/domain/review.ts` + `views/ReviewView.vue`（用户所见）

---

## 开发约定

### 新增功能时的落点

| 需求 | 改动路径（按顺序） |
|---|---|
| **新增校验规则** | `rules/a11_registry.py` → `rules/a11_engine.py`（加 `_rule_NN`）→ 基线 `.xls` 补对应源行 → 补 unit 测试 |
| **调整规则内容** | 走界面「模板管理」（无需改代码，推荐） |
| **新增 API** | `services/` → `api/routes/` → `api/errors.py` 登记错误码 → `api/app.py` 装配 → `api/client.ts` → `stores/` → `views/` + `router/index.ts` → 补测试 |
| **新增文件格式** | `parsers/<fmt>.py` → `services/staging.py` 的 `_FORMAT_BY_EXTENSION` 与签名探测 → `api/app.py` 注册 → 补 integration 测试 |

### 必须遵守的约束

1. **禁止回写源文件** —— 原报告与源模板永远只读；一切产出都是新文件
2. **不得臆造外部标准** —— 缺标准时输出 `NEEDS_REVIEW` 并说明「未提供标准」，不得推断
3. **每条不符合项必须有证据或缺失材料清单** —— 门禁 G5 会强制校验
4. **切片留痕** —— 每个功能切片应同时产出 `specs/`（设计）、`plans/`（计划）、`evidence/`（证据）三类文档
5. **不改已完成修订** —— `review_revisions` 与已发布模板规则快照不可变，只能新增版本

---

## License

内部项目，暂未指定开源协议。
