# 模板操作审计 —— 运行态验证证据

日期：2026-09-20
服务地址：`http://127.0.0.1:8766/`
数据库：SQLite，Alembic `0004 (head)`
验证方式：真实 HTTP 请求（非 ASGI 内存客户端）

## 1. 结论

| 验证项 | 结论 |
|---|---|
| `GET /api/templates/{id}/audit-events` 模板规则管理可用 | **GO** —— HTTP 200，返回 6 条事件 |
| 同一接口测试报告审核被拒 | **GO** —— HTTP 403 `PERMISSION_DENIED` |
| 未建立会话被拒 | **GO** —— HTTP 401 `AUTHENTICATION_REQUIRED` |
| 六个受审动作各产生且仅产生一条事件 | **GO** —— 6 条，最新优先 |
| 操作人由服务端会话决定 | **GO** —— 全部为 `模板规则管理` |
| 前后快照可用且语义正确 | **GO** —— 见第 5 节 |
| 快照不泄漏受管文件绝对路径 | **GO** —— 快照中不存在 `source_path` |
| 源模板与源报告未被修改 | **GO** —— SHA-256 前后一致 |
| 后端 / 前端回归 | **GO** —— 311 passed / 8 skipped；前端 17 passed |
| 手工浏览器人工确认 | **NOT RUN** —— 待人工执行，见第 8 节 |

本切片不改变整体发布决策，整体仍为 **NO-GO**（受真实样本解析覆盖、生产数据库、企业身份认证等未决项约束）。

## 2. 环境与前置

**依赖环境需要重建。** 交接说明中指定的 Codex runtime Python
（`C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`）
本次核查时**不含** `fastapi` / `uvicorn` / `sqlalchemy` / `alembic` / `xlrd` / `olefile` / `pymupdf` / `psutil`，
原项目依赖环境已不可用。因此使用同一 Codex runtime Python 新建了项目虚拟环境：

```powershell
# 已创建：E:\Coding\Hardware-Report-Review-Agent\backend\.venv
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv E:\Coding\Hardware-Report-Review-Agent\backend\.venv
cd E:\Coding\Hardware-Report-Review-Agent\backend
& '.\.venv\Scripts\python.exe' -m pip install -e ".[test]"
```

装得的版本：Python 3.12.14、fastapi 0.141.1、starlette 1.6.0、uvicorn 0.53.0、pydantic 2.13.5、
SQLAlchemy 2.0.54、Alembic 1.20.0、pytest 9.1.1、xlrd 2.0.2、pymupdf 1.28.2、psutil 7.2.2、pywin32 312。

**pytest 默认临时根目录 ACL 已损坏。** `C:\Users\sdt52153\AppData\Local\Temp\pytest-of-SDT52153`
连目录列举与 ACL 读取都被拒绝（`WinError 5`），导致直接运行 `pytest` 出现
`191 errors / PermissionError`。这不是代码缺陷；沿用仓库既有约定改用
`--basetemp=.tmp\pytest-<label>` 后全部通过。

服务启动方式：

```powershell
cd E:\Coding\Hardware-Report-Review-Agent\backend
& '.\.venv\Scripts\python.exe' -m alembic current     # 0004 (head)
& '.\.venv\Scripts\python.exe' -m uvicorn hw_review.api.app:create_app `
    --factory --app-dir src --host 127.0.0.1 --port 8766
```

## 3. 授权边界验证

| # | 会话 | 请求 | 期望 | 实测 |
|---|---|---|---|---|
| 1 | `admin`（模板规则管理） | `GET /api/templates/{A11}/audit-events` | 200 | **200** `{"events":[]}` |
| 2 | `tester`（测试报告审核） | 同上 | 403 | **403** `PERMISSION_DENIED`「当前账号没有模板规则管理权限。」 |
| 3 | `tester` | `GET /api/templates` | 200（只读允许） | **200** |
| 4 | 无会话 | `GET /api/templates/{A11}/audit-events` | 401 | **401** `AUTHENTICATION_REQUIRED`「请先建立本地会话。」 |

会话响应体确认操作人来源：

```
admin  -> {"actor":"模板规则管理","roles":["template"],"role":"admin"}
tester -> {"actor":"测试报告审核","roles":["review"],"role":"tester"}
```

A11 基线模板（`e48edde8-a82d-5831-918d-6822b58318f6`）审计时间线为空，符合预期：
`TemplateService.ensure_baseline()` 创建系统基线时不写入审计事件，只有用户驱动的变更才记账。

## 4. 六动作审计验证（临时模板）

临时模板：`919e0f42-3fa5-49fd-9eea-177c90b43e83`
名称：`审计验证临时模板-20260920-643d62eb`，版本：`A11`，源文件：打包基线 `hardware-test-process-checklist-a11.xls`

| 顺序 | 动作 | 请求 | HTTP | 结果 |
|---|---|---|---|---|
| 1 | 上传模板 | `POST /api/templates` | **201** | `status=DRAFT`，`source_rows=22`，`effective_rules=21` |
| 2 | 修改规则 | `PUT /api/templates/{id}/rules/TR-01` `{"summary":"JIRA项目及链接（审计验证）"}` | **200** | `main_judgment=RULE` 保持不变 |
| 3 | 新增规则 | `POST /api/templates/{id}/rules` `TR-AUDIT-TMP` | **201** | `source_row=null`，`source_sequence=23`（追加在末尾） |
| 4 | 删除规则 | `DELETE /api/templates/{id}/rules/TR-AUDIT-TMP` | **204** | 空响应 |
| 5 | 发布模板 | `POST /api/templates/{id}/publish` | **200** | `status=PUBLISHED` |
| 6 | 停用模板 | `POST /api/templates/{id}/retire` | **200** | `status=RETIRED` |

审计时间线（`GET .../audit-events`，HTTP 200）返回 6 条，**最新优先**：

| 序 | action | rule_id | actor | occurred_at |
|---|---|---|---|---|
| 1 | `TEMPLATE_RETIRED` | — | 模板规则管理 | 2026-09-20T01:52:47.210142Z |
| 2 | `TEMPLATE_PUBLISHED` | — | 模板规则管理 | 2026-09-20T01:52:47.201710Z |
| 3 | `RULE_DELETED` | `TR-AUDIT-TMP` | 模板规则管理 | 2026-09-20T01:52:47.178710Z |
| 4 | `RULE_CREATED` | `TR-AUDIT-TMP` | 模板规则管理 | 2026-09-20T01:52:47.158710Z |
| 5 | `RULE_UPDATED` | `TR-01` | 模板规则管理 | 2026-09-20T01:52:47.130359Z |
| 6 | `TEMPLATE_UPLOADED` | — | 模板规则管理 | 2026-09-20T01:52:46.328170Z |

动作与规则编号序列断言通过：

```
actions   == [TEMPLATE_RETIRED, TEMPLATE_PUBLISHED, RULE_DELETED, RULE_CREATED, RULE_UPDATED, TEMPLATE_UPLOADED]
rule_ids  == [null, null, TR-AUDIT-TMP, TR-AUDIT-TMP, TR-01, null]
actors    == {"模板规则管理"}
```

## 5. 快照正确性与脱敏

每条事件均满足 `before is not None or after is not None`。

| 动作 | before | after | 校验 |
|---|---|---|---|
| `TEMPLATE_UPLOADED` | `null` | `{status: DRAFT, ...}` | 新建语义正确 |
| `RULE_UPDATED` | `TR-01` 全字段 | 同前，仅 `summary` 变化为「JIRA项目及链接（审计验证）」 | **diff 恰好一个字段** |
| `RULE_CREATED` | `null` | `TR-AUDIT-TMP` 全字段 | 新建语义正确 |
| `RULE_DELETED` | `TR-AUDIT-TMP` 全字段 | `null` | 删除语义正确 |
| `TEMPLATE_PUBLISHED` | `status=PUBLISHED`… 实为 `DRAFT` | `status=PUBLISHED` | 状态迁移正确 |
| `TEMPLATE_RETIRED` | `status=PUBLISHED` | `status=RETIRED` | 状态迁移正确 |

模板级快照字段固定为：`name`、`version`、`status`、`source_filename`、`source_sha256`、`source_rows`、`effective_rules`。
规则级快照字段固定为：`rule_id`、`source_row`、`source_sequence`、`summary`、`verifiable_requirement`、
`required_materials`、`main_judgment`、`confirmed_boundary`、`enabled`。

**脱敏**：对 6 条事件的完整 JSON 做子串检查，`absolute_paths_leaked == false` —— 快照中不存在
`source_path`、反斜杠路径或 `storage` 字样，只有 `source_filename`（纯文件名）与 `source_sha256`。

## 6. 清理与不可变性

临时模板已精确清理，删除前已确认模板 ID 与绝对路径：

- 目标 ID：`919e0f42-3fa5-49fd-9eea-177c90b43e83`
- 受管目录：`backend\storage\templates\919e0f42-3fa5-49fd-9eea-177c90b43e83`

删除明细（断言限定在该 `template_id` 上）：

| 表 | 删除行数 | 清理后残留 |
|---|---:|---:|
| `template_audit_events` | 6 | 0 |
| `template_rules` | 22 | 0 |
| `template_versions` | 1 | 0 |

清理后状态：

| 检查 | 结果 |
|---|---|
| `template_versions` 总数 | 1（仅 A11 基线） |
| A11 基线模板 | `e48edde8-…` `PUBLISHED`，`effective_rules=21`，未受影响 |
| `template_audit_events` 总数 | 0 |
| `storage\templates` 子项 | 0 |
| 打包基线模板 SHA-256 | `e70be939ebeb67ca44b9c734a6165dd15fe2f78b0782bdfbe99fab3b3f534445`（清理前后一致，与既有门禁记录一致） |

## 7. 回归证据

| 套件 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `python -m pytest -q --basetemp=.tmp\pytest-audit-verify` | **311 passed, 8 skipped** (98 warnings, 59.38s) |
| 前端测试 | `npm test -- --run` | **8 files / 17 tests passed** |
| 前端类型检查 | `npm run typecheck` | 通过（无输出） |
| 前端生产构建 | `npm run build` | 通过；`TemplateEditorView-BI_qZNuC.js` 7.18 kB |

后端 311 passed / 8 skipped 与本次切片交接记录一致；8 skipped 仍为需要真实 Microsoft Word 的 DOC 环境门禁用例。

前端构建产物核验（`dist/assets/*.js`）：

| 文案 | 所在产物 |
|---|---|
| `模板审计时间线` | `TemplateEditorView-BI_qZNuC.js` |
| `上传模板` / `修改校验项` / `新增校验项` / `删除校验项` / `发布模板` / `停用模板` | `TemplateEditorView-BI_qZNuC.js` |

服务端托管核验：`GET /` 返回 `index-ClfWlZV3.js`（与本次构建产物一致），
`GET /templates/{id}` 命中 SPA history 回退并返回同一入口，说明运行态为 Vue 构建而非 `prototype/a11-ui` 兜底。

前端接线位置：`api/client.ts:110 listTemplateAuditEvents()`、`stores/templates.ts:26-31`（与模板详情并行加载）、
`views/TemplateEditorView.vue:84-89`（`audit-panel` / `audit-timeline` 时间线，显示动作、变更摘要、操作人、时间、规则编号）。

## 8. 未完成与未验证

- **手工浏览器人工确认：未执行。** 需要在浏览器中由人工完成：以「模板规则管理」打开模板详情页应看到
  「模板审计时间线」；修改规则后刷新页面记录仍在；以「测试报告审核」访问审计接口应被拒绝。
  已打开预览地址供人工核对：`http://127.0.0.1:8766/templates/e48edde8-a82d-5831-918d-6822b58318f6`。
  浏览器自动化此前受本机 ACL 限制，且**自动化通过不等于人工验收通过**，因此本项不得记为已完成。
- A11 基线的审计时间线为空属预期行为（系统基线不产生用户操作事件），本次已确认，不代表审计缺失。
- 生产身份提供方（OIDC / LDAP / SSO）仍未接入；当前仅为回环地址可用的本地签名 Cookie 会话，
  生产认证门禁保持 **NO-GO**。
- 真实大模型调用、OCR、DOCX/XLSX 真实样本兼容、生产数据库选型、备份恢复、并发验证、
  真实 Office/WPS 导出兼容、生产数据保留制度均未验证，本切片不涉及。
