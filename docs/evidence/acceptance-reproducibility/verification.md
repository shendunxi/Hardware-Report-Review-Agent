# 验收可复现性 —— 验证证据（S2）

日期：2026-09-20
切片：S2（对应 `docs/superpowers/specs/2026-09-20-acceptance-reproducibility-design.md`）
目标：消除 B4 —— 验收 manifest 内嵌 17 条本机绝对路径与 `source_root`

## 1. 结论

| 目标 | 结论 | 关键证据 |
|---|---|---|
| manifest 不再携带机器路径 | **GO** | 17 条 `absolute_path` 与 `source_root` 全部移除；`absolute_path` / 反斜杠分隔符的断言已加入测试 |
| 样本根由运行时供给 | **GO** | `--sample-root` 与 `HW_REVIEW_SAMPLE_ROOT` 双通道；两者皆缺时 `main` 以退出码 2 拒绝 |
| 相对路径不能逃出样本根 | **GO** | 绝对路径、盘符、`/` 开头、`..` 穿越、空值均被 `SamplePathError` 拒绝 |
| 生成的证据不含机器路径 | **GO** | `manifest` / `sample_root` / `files[].path` 全部记录可移植值；实测输出中无 `C:\` 或 `E:\` |
| 任何目录都能跑通 | **GO** | 占位样本树 + **相对根**跑通真实 CLI，产出全部 3 个产物，门禁画像与真实运行一致 |

**注意**：真实样本仍然不可用（B5），所以本切片只证明「runner 与机器解耦」，**不能**解释为 G2/G3 已被修复。

## 2. 契约变更摘要（manifest schema 1.0 → 1.1）

由脚本从原始文件**保真派生**，未手工转写路径：

```
samples: 17
unique_ids: 17
groups: 15
primary: 15
alternates: 2
absolute_path_present: False
source_root_present: False
backslash_path_present: False
ids_unchanged: True
paths_unchanged_modulo_separator: True
first_rel: HPYR2D/DS/HYR2D DS Project Hardware Test Report（DVB-C for Overseas）V1.23-0327.xls
last_rel:  TFY03/PP/TFY03 PP项目硬件测试报告(FTTR)-V1.3.xls
```

17 / 15 / 15 / 2 的完整性约束未放宽。`relative_path` 此前是**未被任何代码读取的死数据**，现成为唯一数据源。

## 3. 回归

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `python -m pytest -q --basetemp=.tmp\pytest-s2-full` | **311 passed, 8 skipped** |
| 验收测试子集 | `pytest tests/acceptance` | **4 passed, 2 skipped** |
| 改动前基线 | 同上 | 311 passed / 8 skipped（**数量一致**：仅扩展断言，未新增用例） |
| 静态检查 | IDE 诊断（runner + 2 个验收测试） | 0 问题 |

被跳过的 2 项仍是 opt-in 的发布门禁断言（`HW_REVIEW_REQUIRE_ALL_FROZEN_SAMPLES`），与本次改动无关。

**过程中被测试抓出的缺陷**：第一次改动漏掉了第二处 `Path(sample["absolute_path"])`（运行后独立指纹复核段），由 `test_acceptance_runner.py` 以 `KeyError: 'absolute_path'` 直接暴露后修正。这说明 manifest 契约变更已被测试真正守住。

## 4. 路径安全断言

在既有 `test_acceptance_runner.py::test_failed_parse_still_records_elapsed_time_and_memory` 中扩展：

**接受**（分隔符兼容）

```python
assert resolve_sample_path(tmp_path, "nested\\source.xls") == tmp_path / "nested" / "source.xls"
assert resolve_sample_path(tmp_path, "nested/source.xls") == tmp_path / "nested" / "source.xls"
```

**拒绝**（逐项 `pytest.raises(SamplePathError)`）

| 输入 | 拒绝理由 |
|---|---|
| `C:\Windows\win.ini` | 盘符 |
| `/etc/passwd` | POSIX 绝对路径 |
| `../outside.xls` | 向上穿越 |
| `nested/../../outside.xls` | 向上穿越（先于解析判定） |
| `""` | 空值 |

**分层行为**：`_load_manifest` fail fast（manifest 级缺陷不产出可疑证据）；`_parse_samples` 逐条解析，`SamplePathError` 记为该文件的 `SOURCE` / `INVALID_SAMPLE_PATH` 后继续 —— 保持 runner 既有的逐文件容错：

```python
assert escaped_records[0]["error_stage"] == "SOURCE"
assert escaped_records[0]["error_code"] == "INVALID_SAMPLE_PATH"
```

**缺根拒绝**：清空 `HW_REVIEW_SAMPLE_ROOT` 后调用 `main`（不带 `--sample-root`）→ `SystemExit(2)`，即 CLI 层直接拒绝，不会静默产出一份依赖本机的结果。

## 5. 可移植性实证（占位样本树）

在 `backend/.tmp/s2-samples/` 按 manifest 的 17 个相对路径生成占位文件（`.xls` 用 xlwt、`.pdf` 用 pymupdf 真实生成、`.doc` 因本机无 Word 只能放占位字节），然后以**相对根**驱动真实 CLI：

```powershell
python -m hw_review.acceptance.run_samples `
  --manifest tests/acceptance/sample_manifest.json `
  --sample-root .tmp/s2-samples `
  --output .tmp/s2-acceptance-output
```

结果：

```json
{
  "placeholder_files_created": 17,
  "exit_code": 1,
  "overall_decision": "NO-GO",
  "gates": { "G1": "GO", "G2": "NO-GO", "G3": "NO-GO",
             "G4": "GO", "G5": "GO", "G6": "GO", "G7": "GO", "G8": "GO" },
  "files_recorded": 17,
  "groups_recorded": 15,
  "parse_successes": 15,
  "portability": {
    "manifest_field": "tests\\acceptance\\sample_manifest.json",
    "sample_root_field": ".tmp\\s2-samples",
    "first_file_path": "HPYR2D/DS/…V1.23-0327.xls",
    "absolute_path_key_absent": true,
    "drive_letter_absent": true,
    "no_resolved_tree_in_output": true
  },
  "artifacts": ["release-gates.md", "sample-results.json", "sample-results.md"]
}
```

两点值得注意：

1. **门禁画像与真实运行完全一致**（G1/G4/G5/G6/G7/G8 = GO，G2/G3 = NO-GO）。这既说明 runner 从任意根行为一致，也说明**唯一的解析阻塞仍然只是 `.doc`** —— 占位树里只有那 2 个 `.doc` 失败，与真实机器上的 G2 阻塞同源。
2. **输出中不含任何机器路径**：`manifest` 与 `sample_root` 记录调用方原值，`files[].path` 记录 manifest 相对路径，`SOURCE_NOT_FOUND` 的消息也改用相对路径。

## 6. 副产品：G6/G8 的陈旧性被当场抓到

本次占位运行中 **G6 与 G8 报告 GO**，但它们读取的是仓库内 `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-7|8-report.md` 的**历史文本**（`"274 passed"`、`"1440x900"`），与这次运行毫无关系 —— 这次运行连 17 个真实样本都没有。

这不是 S2 的缺陷（该机制读仓库内文件，行为与机器无关），但它把「字面量抓取」的问题**具体化**了：门禁可以在完全不相干的运行中报 GO。改造成结构化证据需要一个当前尚无消费者的产物格式，按其生产环节一并设计，**延后到 S4**（见 spec §6）。

## 7. 遗留与未验证

- **未修改历史产物** `docs/evidence/a11-local-vertical-slice/sample-results.json`：它仍含
  `"source_root": "D:\\Document\\AI创新应用大赛\\…"` 与绝对 `"manifest"` 字段。它是 2026-09-11 那一次运行的历史证据，按 spec §8 保留原样，**不再代表新的运行契约**。若后续重跑该切片，新产物将不再包含机器路径。
- 未在**真实样本树**上运行（B5：本机无样本目录，且 DOC 需 genuine Microsoft Word）。
- 未在**非 Windows 平台**实机运行；跨平台分隔符由单元断言覆盖（`nested\source.xls` 与 `nested/source.xls` 等价），未做 Linux/macOS 实测。
- `G6`/`G8` 未改造，仍为字面量抓取。
- 未执行真实浏览器人工验收；未做任何 Git 操作。
