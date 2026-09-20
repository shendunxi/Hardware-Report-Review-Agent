# 验收可复现性设计（S2）

日期：2026-09-20
状态：已确认

## 1. 目标与边界

消除 B4：`backend/tests/acceptance/sample_manifest.json` 内嵌 17 条 `D:\Document\...` 绝对路径与一个 `source_root`，导致

1. 验收矩阵只能在该样本目录恰好存在的机器上运行；
2. 本机目录结构被写入版本库（`docs/evidence/a11-local-vertical-slice/sample-results.json` 同样回写了该路径）。

**不涉及**：G1–G8 的判定语义与数量、解析器、规则引擎、任务生命周期、`_parse_samples` 的逐文件容错设计。

## 2. 契约变更（manifest schema 1.0 → 1.1）

| 字段 | 变更 |
|---|---|
| `source_root` | **删除** |
| `samples[].absolute_path` | **删除** |
| `samples[].relative_path` | **改为唯一数据源**（此前是未被读取的死数据） |
| `samples[].relative_path` 分隔符 | 统一写为 `/`；代码同时接受 `\`（兼容既有写法） |
| 其余字段 | 不变（`id` / `group_id` / `role` / `expected_extension`） |

样本根由外部供给，优先级：

1. `--sample-root PATH`（CLI 参数）
2. `HW_REVIEW_SAMPLE_ROOT`（环境变量）
3. 两者皆缺 → **立即失败**，错误信息同时给出两种用法

## 3. 路径安全

`relative_path` 必须解析到样本根**之内**。拒绝以下情形：

- 绝对路径与盘符（`C:\...`、`/abs/...`、UNC）
- 向上穿越（任一 `..` 段）
- 解析后 `relative_to(sample_root)` 失败（兼容符号链接等间接逃逸）

理由：删除绝对路径后，`relative_path` 成为唯一入口，若不加约束，manifest 仍可指向磁盘任意位置。本约束与 `services/staging.py` 的 `UNSAFE_WORKSPACE`、`services/cleanup.py` 的 UUID 白名单属同一防御风格。

**分层行为**：

- `_load_manifest`：对每条目调用解析器 → **fail fast**（manifest 级缺陷，不产出可疑证据）
- `_parse_samples`：逐条解析，`ValueError` 记为该文件的 `SOURCE` / `INVALID_SAMPLE_PATH` 失败后继续 → 保持 runner 既有的逐文件容错

## 4. 输出与脱敏

| 字段 | 变更 |
|---|---|
| `source_root`（输出） | 改名为 `sample_root`，记录**调用方提供的原值**，不做 `resolve()` |
| `manifest`（输出） | 同样记录调用方提供的原值，不再 `resolve()` |
| `files[].path` | 由**解析后的绝对路径**改为 **manifest 的 `relative_path`** |
| `SOURCE_NOT_FOUND` 的消息 | 由绝对路径改为 `relative_path` |

目的：提交到 `docs/evidence/` 的产物不再携带本机绝对路径。代价是证据的绝对可追溯性下降——由 spec 显式接受，操作方如需可追溯应传入相对路径或在运行记录中另行说明。

`schema_version` 由 `1.0` 升为 `1.1`。

## 5. 保留的不变式（不得放宽）

- `_load_manifest` 仍强制：**恰好 17 条样本**、**恰好 15 个业务组**、`id` 唯一
- `_parse_samples` 仍**不**施加 17/15 约束（既有单测以 1 条样本直接调用它）
- `_build_gates` 的 8 个门禁与判定条件不变
- 源文件只读：仍以「暂存前后指纹一致」为 G1 依据

## 6. 明确延后（不属 S2）

G6/G8 目前通过抓取 `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-7|8-report.md`
中的字面量（`"274 passed"`、`"1440x900"`）判定。该机制**已老化**（后端现为 311 passed），但读取的是**仓库内文件**，在任何机器上行为一致，**因此不是可复现性缺陷**。

改造成结构化证据需要一个当前尚无消费者的产物格式（谁产出套件/浏览器证据）。该设计应与其生产环节一并确定，**延后到 S4（真实样本验收）**。

## 7. 验证方式

约束：不新增测试文件或测试用例，只扩展既有测试的断言。

| 目标 | 位置 |
|---|---|
| manifest 契约由 `absolute_path` 改为 `relative_path` | `tests/acceptance/test_frozen_samples.py::test_manifest_freezes_seventeen_inputs_and_fifteen_business_groups`（同一条测试，契约更新） |
| `_parse_samples` 新签名 + 路径逃逸/缺根拒绝 | `tests/acceptance/test_acceptance_runner.py::test_failed_parse_still_records_elapsed_time_and_memory` |
| 不再依赖任何机器路径 | 用**占位样本树**（17 文件 / 15 组 / 2 个 COMPATIBILITY_ALTERNATE）在任意目录跑通 `run_samples`，产出 `sample-results.{json,md}` 与 `release-gates.md` |

## 8. 交付物

- 修改：`backend/src/hw_review/acceptance/run_samples.py`、`backend/tests/acceptance/sample_manifest.json`、`backend/tests/acceptance/test_frozen_samples.py`、`backend/tests/acceptance/test_acceptance_runner.py`、`README.md`
- 新增：本 spec、`docs/superpowers/plans/2026-09-20-acceptance-reproducibility.md`、`docs/evidence/acceptance-reproducibility/verification.md`
- 不做：Git 操作；不改 `docs/evidence/a11-local-vertical-slice/sample-results.json`（历史产物，保留原样，其路径泄漏在证据文档中声明）
