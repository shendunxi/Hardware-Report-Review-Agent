# Word 自动化宿主策略验证（2026-09-20）

## 1. 决策与范围

用户决定：**DOC 支持 WPS**，本机不安装 Microsoft Word。因此新增「转换器信任策略」，
把原先硬编码的 `Microsoft Word only` 变成可配置项，并把**实际使用的转换宿主**写入证据。

| 项 | 值 |
|---|---|
| 决策人 | 用户 |
| 默认策略 | `microsoft_only`（保持验收级行为不变） |
| 本次启用的策略 | `any_word_compatible`（开发通道） |
| 开关 | `HW_REVIEW_WORD_AUTOMATION_POLICY` |

本切片不修改审核规则、判定语义、模板状态规则或导出格式，不新增测试文件或测试用例。

## 2. 环境取证（为什么需要这个开关）

| 探针 | 结果 |
|---|---|
| `HKCR\Word.Application\CLSID` | `{000209FF-0000-0000-C000-000000000046}` |
| `HKCR\Word.Application\CurVer` | `Word.Application.12`；伴生 `.ksobak = Word.Application.11` |
| `HKCR\CLSID\{000209FF-...}` | **不存在**（真实 Word CLSID 为 `{00020906-...}`） |
| `registered_word_server()` | `C:\PROGRA~2\Kingsoft\WPS Office\12.8.2.18581\office6\wps.exe /Automation` |
| `winword.exe` | 未安装 |

WPS 不仅注册了自身的 `KWPS.Application` / `WPS.Application`，还**接管了 `Word.Application`
这个名字**，并把友好名伪造成「Microsoft Office Word 应用程序」。`.ksobak` 后缀是 WPS 改写
注册表时留下的原始值备份（kso = Kingsoft Office）。

因此 `WordWorker` 的原有守卫（要求注册路径含 `winword.exe`）会把本机判定为
「Microsoft Word COM server is unavailable」。这不是技术不能，是既有的信任边界。

## 3. WPS 转换质量交叉验证

方法：用 WPS 转换 `.doc`，与该报告**已冻结的真实 `.pdf`**（同一份报告的另一种格式）
逐页比对 `get_text("text")` 归一化文本，并比对页数与 PDF 体积。

### R-06 —— `S-06 .doc`（25,950,107 B）对比冻结的 `S-07 .pdf`

| 指标 | 值 |
|---|---|
| 页数 | 55 / 55（一致） |
| 逐页文本完全一致 | **55 / 55** |
| PDF 体积 | 3,140,794 B（WPS） vs 3,139,592 B（冻结）→ 差 +0.04% |
| 结构化产物 | paragraphs=904，tables=33 |
| 耗时 | 17.9–36.5 s |
| 源文件 sha256 前后 | 一致（未修改） |

### R-13 —— `S-14 .doc`（10,613,760 B）对比冻结的 `S-15 .pdf`

| 指标 | 值 |
|---|---|
| 页数 | 43 / 43（一致） |
| 逐页文本完全一致 | 28 / 43 |
| 差异页的字符数差 | 每页 1–13 字符（如 3763 vs 3776、308 vs 309） |
| PDF 体积 | 2,275,856 B（WPS） vs 3,011,661 B（冻结）→ 差 **−24.4%** |
| 结构化产物 | paragraphs=1054，tables=36 |
| 耗时 | 22.9–40.0 s |
| 源文件 sha256 前后 | 一致（未修改） |

**结论**：

- R-06 上 WPS 与冻结产物的文本层**完全等价**，PDF 体积差 0.04%。
- R-13 页数与文本高度接近，但 **PDF 体积小 24.4%**。体积差异最可能来自图片压缩/分辨率，
  尚未归因。这意味着 WPS 产物在「版面视觉证据」上不能默认视为与 Word 等价。
- 因此本策略只能作为**开发/试运行通道**，不能据此声明 DOC 格式的验收级兼容。

## 4. 实现范围

| 文件 | 变更 |
|---|---|
| `backend/src/hw_review/parsers/word_worker.py` | 新增 `POLICY_MICROSOFT_ONLY` / `POLICY_ANY_WORD_COMPATIBLE` / `WORD_AUTOMATION_POLICIES`；`WordWorker(policy=...)`；守卫改为按策略生效；`ConversionArtifacts.automation_host` |
| `backend/src/hw_review/config.py` | 新增 `word_automation_policy`，环境变量 `HW_REVIEW_WORD_AUTOMATION_POLICY` |
| `backend/src/hw_review/parsers/doc.py` | `DocParser(word_policy=...)`；`ConversionProvenance.automation_host` 透传 |
| `backend/src/hw_review/domain/models.py` | `ConversionProvenance.automation_host` |
| `backend/src/hw_review/api/app.py` | 把 `settings.word_automation_policy` 注入两个 `DocParser` |
| `backend/tests/integration/test_doc_parser.py` | 扩展既有断言：放行策略必须到达启动步骤、未知策略必须被拒绝、真实 DOC 测试改为按策略跳过并断言 `automation_host` |
| `backend/pyproject.toml` | `addopts = "--basetemp=.tmp/pytest"`（见第 6 节） |
| `backend/tests/integration/{test_xls_parser,test_pdf_parser,test_doc_parser}.py` | 样本根目录改为读取 `HW_REVIEW_SAMPLE_ROOT`，修正原先指向不存在目录的硬编码路径 |

### 关键设计点：`automation_host`

WPS 上报的 `Application.Version` 是 `12.0`，与真实 Word 无法区分。若不记录宿主，
一份由 WPS 产出的 DOC 证据在数据里与 Word 产物**完全无法分辨**，直接违背「证据可追溯」。
因此 `ConversionArtifacts` 与 `ConversionProvenance` 都增加 `automation_host`，
由父进程从注册表读取并写入（空值表示策略引入之前的历史证据）。

## 5. 验证结果

环境：`.venv`（Python 3.12 / pytest 9.1.1），工作目录 `backend`。

| 场景 | 结果 |
|---|---|
| 默认策略（`microsoft_only`）全量回归 | **313 passed, 6 skipped** |
| 放行策略（`any_word_compatible`）全量回归 | **315 passed, 4 skipped** |

两个真实 DOC 样本在放行策略下**真正执行并通过**：

```
S-06  page_count=55  text=904  table=33  image=94  duration=36.5s
      word_version=12.0  automation_host=...Kingsoft\WPS Office\...\wps.exe /Automation
S-14  page_count=43  text=1054 table=36  image=59  duration=40.0s
      word_version=12.0  automation_host=...Kingsoft\WPS Office\...\wps.exe /Automation
```

两个样本的源文件 sha256 与大小在前后完全一致（源文件保护保持成立）。

剩余 4 个 skip 全部有明确归因：

| skip | 原因 | 结论 |
|---|---|---|
| `test_frozen_samples.py:62`、`:70` | 门禁断言为 opt-in | 设计如此 |
| `test_doc_parser.py` ×2 | 符号链接需 `SeCreateSymbolicLinkPrivilege`（WinError 1314） | 需管理员或开发者模式 |

## 6. 顺带修复的问题

| 问题 | 影响 | 处理 |
|---|---|---|
| 3 个真实样本集成测试硬编码了**不存在**的样本根目录（多一层 `硬件测试报告审核智能体`） | `S-01`、`S-07` 的真实样本测试**从未执行**；`S-06`/`S-14` 以错误的理由跳过。此前报告的 8 个 skip 中有 4 个属此类 | 改为读取 `HW_REVIEW_SAMPLE_ROOT`，默认值更正 |
| `%TEMP%\pytest-of-<user>` 目录 ACL 损坏（存在、为空、`os.scandir` 拒绝访问） | 文档中的 `python -m pytest -q` 直接报 62 errors | `addopts = "--basetemp=.tmp/pytest"` 绕开 |

## 7. 未关闭项

- WPS 产物**不是验收级证据**。整体发布决策仍为 **NO-GO**，DOC 门禁的正式措辞待用户确认。
- R-13 的 PDF 体积差异（−24.4%）尚未归因，未确定是否影响版面视觉证据。
- 未安装 genuine Microsoft Word；`microsoft_only` 策略在本机无法跑通 DOC。
- 未执行真实浏览器人工验收；自动化通过不等于人工验收通过。
- 生产身份提供方（企业微信）尚未接入；仍为回环可用的本地签名 Cookie 会话。
- 真实大模型调用、生产数据库、备份恢复、并发验证、真实 Office/WPS 导出兼容、
  生产数据保留制度均未验证，本切片不涉及。
