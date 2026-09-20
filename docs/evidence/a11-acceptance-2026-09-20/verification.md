# A11 完整验收运行记录（2026-09-20）

本目录是 2026-09-20 两次完整 `run_samples` 运行的产物，**未覆盖** 2026-09-11 的历史证据
（[`../a11-local-vertical-slice/`](../a11-local-vertical-slice/) 按 spec §8 保留原样）。
最终一次为 `run_id = 20260920T072513Z`。

## 1. 运行命令与环境

```powershell
cd backend
$env:PYTHONPATH = "src"
$env:HW_REVIEW_WORD_AUTOMATION_POLICY = "any_word_compatible"   # 本机无 Microsoft Word

python -m hw_review.acceptance.run_samples `
  --manifest tests/acceptance/sample_manifest.json `
  --sample-root .tmp/samples `
  --output ../docs/evidence/a11-acceptance-2026-09-20
```

退出码 `1`（整体 NO-GO，见第 2 节）。

`--sample-root` 传的是**相对路径** `backend/.tmp/samples`，它是指向冻结样本树的目录 junction。
这样写的原因见第 4 节：runner 按设计「记录调用方提供的原值」，传绝对路径会把本机路径写进证据。

## 2. 结果：整体 GO

| 门禁 | 结论 | 证据来源 |
|---|---|---|
| G1 Source protection | **GO** | 本次运行计算 — 17/17 指纹未变 |
| G2 Readability | **GO** | 本次运行计算 — 17/17 解析成功 |
| G3 Structural completeness | **GO** | 本次运行计算 |
| G4 Rule completeness | **GO** | 本次运行计算 — 15/15 组各 21 条结果 |
| G5 Traceability | **GO** | 本次运行计算 |
| G6 Lifecycle | **GO** | [`../gate-evidence/gates.json`](../gate-evidence/gates.json) — `passed=313 failed=0 skipped=6 recorded_at=2026-09-20T06:27:53+00:00` |
| G7 Performance | **GO** | 本次运行计算 — 全部 ≤1200 秒 |
| G8 UI | **GO** | 同一证据文件 — `browser_verified=true`，三视口齐备；真实浏览器证据见 [`../a11-browser-verification-2026-09-20/`](../a11-browser-verification-2026-09-20/) |

**整体发布决策：GO**（`run_id = 20260920T072513Z`，退出码 `0`）。

G1–G5、G7 由本次运行直接计算；G6、G8 来自结构化、带日期的补充证据
[`../gate-evidence/gates.json`](../gate-evidence/gates.json)，
不再是对历史文档做子串匹配的结果。

产物中的 `word_automation_policy = any_word_compatible` 使这份结果自带限定：
G2/G3 的 GO 成立在 **WPS 开发通道** 上。换回默认 `microsoft_only`，同一台机器同一份样本
回到 15/17（G2/G3 = NO-GO）。

## 3. 文件矩阵（17/17 SUCCESS，全部源文件未变）

| ID | 组 | 类型 | 格式 | 容器 | 文本 | 表格 | 图片 | 秒 |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| S-01 | R-01 | PRIMARY | XLS | 18 | 0 | 18 | 0 | 0.7 |
| S-02 | R-02 | PRIMARY | XLS | 4 | 0 | 4 | 0 | 0.3 |
| S-03 | R-03 | PRIMARY | XLS | 14 | 0 | 14 | 0 | 0.7 |
| S-04 | R-04 | PRIMARY | XLS | 20 | 0 | 20 | 0 | 3.0 |
| S-05 | R-05 | PRIMARY | XLS | 28 | 0 | 28 | 0 | 1.1 |
| S-06 | R-06 | PRIMARY | DOC | 55 | 904 | 33 | 94 | 36.2 |
| S-07 | R-06 | ALTERNATE | PDF | 55 | 627 | 46 | 94 | 4.2 |
| S-08 | R-07 | PRIMARY | XLS | 18 | 0 | 18 | 0 | 5.0 |
| S-09 | R-08 | PRIMARY | XLS | 27 | 0 | 27 | 0 | 1.1 |
| S-10 | R-09 | PRIMARY | XLS | 5 | 0 | 5 | 0 | 0.1 |
| S-11 | R-10 | PRIMARY | XLS | 16 | 0 | 16 | 0 | 4.6 |
| S-12 | R-11 | PRIMARY | XLS | 22 | 0 | 22 | 0 | 1.1 |
| S-13 | R-12 | PRIMARY | PDF | 25 | 521 | 14 | 37 | 3.1 |
| S-14 | R-13 | PRIMARY | DOC | 43 | 1054 | 36 | 59 | 38.8 |
| S-15 | R-13 | ALTERNATE | PDF | 43 | 573 | 38 | 59 | 4.6 |
| S-16 | R-14 | PRIMARY | XLS | 18 | 0 | 18 | 0 | 3.6 |
| S-17 | R-15 | PRIMARY | XLS | 23 | 0 | 23 | 0 | 1.5 |

合计：解析 109.8 秒 + 规则 7.2 秒 ≈ **117 秒**跑完 17 份文件；最慢单文件 38.8 秒（S-14，DOC）。

### DOC 与其配对 PDF 的交叉印证

| 组 | DOC（WPS 转换） | 配对 PDF | 一致项 |
|---|---|---|---|
| R-06 | 55 容器 / 94 图片 | 55 容器 / 94 图片 | 页数、**图片数**完全一致 |
| R-13 | 43 容器 / 59 图片 | 43 容器 / 59 图片 | 页数、**图片数**完全一致 |

两组配对文件的页数与图片数逐一相同。这与
[`../word-automation-policy/verification.md`](../word-automation-policy/verification.md)
的逐页文本比对互相印证：WPS 转换在**内容完整性**上未见缺失。
R-13 那份 24.4% 的 PDF 体积差异因此更可能来自图片压缩/分辨率而非内容丢失，
但**尚未归因**，不作为版面视觉等价的依据。

## 4. 证据脱敏

| 产物 | 机器路径 |
|---|---|
| `sample-results.json` | **none** |
| `sample-results.md` | **none** |
| `release-gates.md` | **none** |

`manifest` 记录为 `tests\acceptance\sample_manifest.json`，`sample_root` 记录为 `.tmp\samples`，
均为可移植值。

首次运行时传入的是绝对路径 `D:\...`，导致 `sample_root` 字段带出本机路径。这不是 runner 缺陷：
spec §4 明确设计为「记录调用方提供的原值，不做 `resolve()`」，并把「入库时传入相对路径」定为
操作方责任。本次按该约定改用仓库内 junction 的相对路径重跑，泄漏已消除。

## 5. G6 / G8 的重构（本次核心变更）

### 变更前

`_build_gates` 直接读取 2026-09-11 的历史报告并做**子串匹配**：

```python
task7_text = (repository_root / ".superpowers/sdd/2026-09-11-.../task-7-report.md").read_text(...)
lifecycle = "45 passed" in task7_text and "274 passed" in task7_text
task8_text = (repository_root / ".superpowers/sdd/2026-09-11-.../task-8-report.md").read_text(...)
ui_ok = "44 passed" in task8_text and "1440x900" in task8_text and "760x900" in task8_text
```

后果：两个门禁与当前代码**完全解耦**。当前后端回归是 313 passed，与 `274 passed` 无关；
即使测试全挂、即使从未启动过浏览器，两项依然报 GO。上一版运行因此得到了一个
**8/8 全 GO** 的结论，其中 2 项是虚的。

### 变更后

runner 对无法由自身运行判定的门禁**弃权**，改为消费结构化、带日期的补充证据：

- 新增状态 `NOT_RUN`。G6/G8 的证据缺失、不可读、schema 不匹配时一律 `NOT_RUN`，
  整体决策因而不是 `GO`。
- 证据文件：`docs/evidence/gate-evidence/gates.json`（可用 `HW_REVIEW_GATE_EVIDENCE` 覆盖路径）。
- G6 判据：`lifecycle.failed == 0` 且 `lifecycle.passed >= 100`（下限，防止空套件通过）
  且 `recorded_at` 在 30 天窗口内。
- G8 判据：`ui.browser_verified is True` 且 `ui.viewports` 覆盖
  `1440x900` / `1280x720` / `760x900` 且 `recorded_at` 在 30 天窗口内。
- `release-gates.md` 的固定链接改为指向该证据文件与本运行记录，不再指向历史 task 报告。

### fail-closed 验证矩阵

以 `reference = 2026-09-20T06:30Z` 逐项验证：

| 场景 | G6 | G8 | 说明 |
|---|---|---|---|
| 证据文件缺失 | NOT_RUN | NOT_RUN | |
| 文件不存在（路径写错） | NOT_RUN | NOT_RUN | |
| 内容非 JSON | NOT_RUN | NOT_RUN | |
| `schema_version` 不匹配 | NOT_RUN | NOT_RUN | |
| 一切皆过期（90 天前） | NO-GO | NO-GO | 过期即不采纳 |
| 套件 `failed=2` + 只报 1 个视口 | NO-GO | NO-GO | |
| 空套件 `passed=3` | NO-GO | GO | 通过下限拦住 |
| 全部满足 | GO | GO | |

对照随仓库发布的真实证据文件（仓库根解析）：

```
note : supplementary gate evidence accepted
G6   : GO     backend suite passed=313 failed=0 skipped=6 recorded_at=2026-09-20T06:27:53+00:00
G8   : NO-GO  browser_verified=False recorded_at=None missing viewports=[...]
```

## 6. 本次修复的另外两个缺口

### 6.1 runner 没有接入转换器信任策略

首次运行得到 G2 = NO-GO（15/17）。原因：`_parse_samples` 自行构造
`DocParser(timeout_seconds=MAX_GATE_SECONDS)` 而**没有传转换器策略**，于是吃默认的
`microsoft_only`，两个 DOC 在 0.05 秒内被注册表守卫拒绝（`PARSING/DOC_CONVERSION_FAILED`）。
即：Word 宿主策略此前只接到了 `api/app.py`，漏了验收 runner。

修复：`_parse_samples(..., word_policy=None)` 与 `run(..., word_policy=None)`，默认回落到
`get_settings().word_automation_policy`；产物新增顶层字段 `word_automation_policy`，
`sample-results.md` 头部与 CLI 输出同步展示，使「这份结论由哪个转换器产生」成为证据的一部分。

### 6.2 冻结样本契约测试校验的是历史产物

`tests/acceptance/test_frozen_samples.py` 把结果路径硬编码为
`docs/evidence/a11-local-vertical-slice/sample-results.json`（2026-09-11 那一次）。
也就是说，这些契约测试一直在描述一份与当前代码不再对应的产物。

修复：改为解析**最新的** `docs/evidence/a11-acceptance-*/sample-results.json`，
并提供 `HW_REVIEW_FROZEN_RESULTS` 覆盖；两者皆无时才回落到历史路径。

## 7. 回归

| 场景 | 结果 |
|---|---|
| 后端全量（默认策略 `microsoft_only`） | **313 passed, 6 skipped, 0 failed** |
| 后端全量（`any_word_compatible`，见 word-automation-policy 记录） | 315 passed, 4 skipped |

6 个 skip 全部可归因：2 个是 `test_frozen_samples` 的 opt-in 门禁断言，
2 个需要 `SeCreateSymbolicLinkPrivilege`，2 个需要 genuine Microsoft Word。

## 8. 未关闭项

- **G8 的 GO 建立在自动化浏览器证据上**，该口径由项目负责人于 2026-09-20 明确接受。
  证据是真实 Chrome 在三个视口下的完整流程，**未做人工视觉验收**。
  残留项：`/favicon.ico` 返回 404；角色不跨整页刷新持久化（客户端路由不受影响）。
- G7 的判据是「单文件 ≤1200 秒」，远松于 PRD 的「单任务 P95 ≤20 分钟 + 并发 C=5」。
  并发下的 P95 **从未测量**，G7 的 GO 不能替代该验收。
- 未安装 genuine Microsoft Word；`microsoft_only` 策略在本机仍无法跑通 DOC。
- WPS 转换的 R-13 PDF 体积差异（−24.4%）未归因。
- 真实大模型调用、OCR、DOCX/XLSX 真实样本、生产数据库、备份恢复、并发验证、
  企业微信身份认证、真实 Office/WPS 导出兼容、生产数据保留制度均未验证。
