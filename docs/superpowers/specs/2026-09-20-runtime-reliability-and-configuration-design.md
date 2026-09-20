# 运行可靠性与配置外部化设计

日期：2026-09-20
状态：已确认（本轮按 S1 目标直接定稿；恢复语义取"租约式重认领"方案，理由见 §2.2）

## 1. 目标与边界

本切片消除三个已确认缺陷与一项加固：

| 编号 | 缺陷 | 证据 |
|---|---|---|
| D1 | 中间态任务永久卡死，无恢复路径 | `services/lifecycle.py:87-94`、`persistence/repositories.py:433-444`、`api/routes/tasks.py:151-153` |
| D2 | `WorkspaceCleaner.clean_expired` 未被任何生产路径调用（死代码） | `services/cleanup.py:54`；`src/` 内仅有 `clean_task` 调用点 |
| D3 | `Settings` 不读环境变量，而 `migrations/env.py` 读 `HW_REVIEW_DATABASE_URL` → 迁移目标库与运行时库可能不一致 | `config.py:16-32` vs `migrations/env.py:19-21` |
| D4 | `auth_mode="disabled"` 对任意来源主机授予双角色 | `api/access.py:107-120` |

**不涉及**：审核业务规则、判定状态语义、导出格式、数据库结构、UI 行为。
**不新增数据库迁移**：复用既有 `tasks.execution_claim` 与 `tasks.updated_at` 列。

## 2. D1 恢复语义 —— 设计决策

### 2.1 问题陈述

`claim_execution` 的守卫是 `WHERE state='CREATED'`，且这是**唯一**认领入口。`execute_claimed` 又要求 `state is FILES_STAGED` 才继续。因此 `{FILES_STAGED, PARSING, PARSED, EVALUATING}` 四个中间态构成死区：

- `POST /api/tasks/{id}/execute` → `owns_execution=False` → 不启动执行
- `execute_claimed` 早退
- 无启动回收、无超时、无重试
- 前端 `isSelectedTransient` 含这四个状态 → **无限轮询**

### 2.2 备选方案与取舍

| 方案 | 做法 | 优点 | 缺点 | 采纳 |
|---|---|---|---|---|
| **A 启动期强制回收** | `create_app` 把中间态置 `FAILED` 并记 `StageFailure(stage="RECOVERY")` | 恢复立即生效；无状态机改动 | ① `FAILED` 语义要求"重新上传"，已暂存文件被清理，用户必须重传；② 多进程部署下会误杀其它 worker 正在执行的任务；③ 启动路径静默改状态 | ✗ |
| **B 租约式重认领** | 认领守卫增加"租约过期"分支 | ① 部署无关，多进程安全；② 不丢数据，可重跑；③ 复用既有 `execution_claim` 列（当前为只写列）；④ 语义单一：租约到期即可被重新认领 | 崩溃后需等待一个租约周期才可重试 | ✓ |

**选择 B。** 方案 A 的"立即恢复"体验更好，但它把"是否多进程"这一部署事实固化进启动路径，并以静默改状态为代价。该判断属于 S3（生产数据库与并发）的职责，不应在本切片预埋。

### 2.3 可认领集合（本切片唯一的状态机不变式变更）

```
claimable(task)  ⇔  state == CREATED
                 ∨  ( state ∈ {FILES_STAGED, PARSING, PARSED, EVALUATING}
                      ∧  now - updated_at ≥ execution_lease_seconds )
```

认领成功后原子地：`state := FILES_STAGED`、`execution_claim := <新令牌>`、`updated_at := now`。

**唯一被放宽的不变式**：允许一次 `中间态 → FILES_STAGED` 的**回退**，且只能由租约重认领触发，条件判断与写入必须在同一条原子 `UPDATE ... WHERE` 内完成。

**不变**：`_NEXT` 映射表与 `_transition()` 行为不做任何修改，不新增合法前向迁移。

### 2.4 为什么 `updated_at` 可以作为租约时钟

`claim_execution` 与每次 `_transition` 都写 `updated_at`。单次评估中**最长无更新的区间**是 `EVALUATING → commit` 之间的 `EvaluationService.evaluate()`，其上限由 DOC 转换超时决定（`DocParser(timeout_seconds=1200)`，`services/evaluation.py` 亦受此约束）。因此：

> **租约必须严格大于最长单次评估耗时。**

- 默认 `execution_lease_seconds = 1800`（1200s 上限 + 50% 余量）
- 必须为正整数，`Settings` 层拒绝非正值
- 若租约过短，仍可能把在跑的任务判为可认领 → 双跑。但见 §2.5：**双跑不会损坏数据**，只是浪费一次解析。这是本设计能容忍租约误差的根本原因。

### 2.5 幂等性论证（重跑安全）

1. 解析只读暂存副本（`FileStager` 已复制并校验指纹），不触碰原报告
2. 规则结果 ID 由 `uuid5(task_id, active_revision_no, rule_id, engine_version, baseline_version)` 派生 → 同一输入必得同一 ID
3. `commit_evaluation` 在**单事务**内「删旧结果 + 插新结果 + 推进状态 + 清 `execution_claim`」
4. 重跑期间 `active_revision_no` 不变

∴ 重跑 N 次与重跑 1 次等价。

### 2.6 可观测性

启动时**不修改任何状态**，但扫描中间态任务并输出 `WARNING`，内容含任务 ID、当前状态、距离可认领的剩余秒数。目的是消除"静默"：运维能立刻看到中断痕迹。

## 3. D2 工作区回收

把 `clean_expired(now)` 接入 `create_app` 启动路径，回收超过 TTL 的孤儿任务工作区。

- 新增 `Settings.workspace_ttl_seconds`，默认 `86400`（24 小时）
- 安全前提：解析在 `EVALUATING` 阶段完成，之后结果已持久化，人工复核**不再需要**工作区。因此 24h TTL 对"仍在执行的任务"是安全的（远大于 1200s 解析上限）
- 回收仅删除 `storage_root` 下**规范的 UUID 直接子目录**（沿用 `WorkspaceCleaner.remove_verified` 既有的符号链接与非直接子目录守卫）
- 回收失败不阻塞启动，记 `WARNING`

## 4. D3 配置外部化

`get_settings()` 改为读取环境变量（前缀 `HW_REVIEW_`）。`Settings` 保持 `frozen` dataclass，**字段默认值一律不变**，以保证现有测试中直接构造 `Settings(...)` 的写法全部继续有效。

| 环境变量 | 字段 | 类型 | 默认 |
|---|---|---|---|
| `HW_REVIEW_DATABASE_URL` | `database_url` | str | `sqlite:///./hw-review.db` |
| `HW_REVIEW_STORAGE_ROOT` | `storage_root` | Path | `./storage` |
| `HW_REVIEW_A11_TEMPLATE_PATH` | `a11_template_path` | Path | 内置资源 |
| `HW_REVIEW_AUTH_MODE` | `auth_mode` | str | `local` |
| `HW_REVIEW_LOCAL_SESSION_SECRET` | `local_session_secret` | str | 开发默认值（仅回环） |
| `HW_REVIEW_LOCAL_SESSION_TTL_SECONDS` | `local_session_ttl_seconds` | int | `28800` |
| `HW_REVIEW_LOCAL_SESSION_COOKIE` | `local_session_cookie` | str | `hw_review_session` |
| `HW_REVIEW_EXECUTION_LEASE_SECONDS` | `execution_lease_seconds` | int | `1800` |
| `HW_REVIEW_WORKSPACE_TTL_SECONDS` | `workspace_ttl_seconds` | int | `86400` |

**与 Alembic 对齐**：`migrations/env.py` 已在读 `HW_REVIEW_DATABASE_URL`；本切片让运行时读同一变量，消除"迁移 A 库、服务连 B 库"。

**启动即失败的强校验（不静默降级）**：

- `auth_mode ∉ {local, disabled}` → 保持现有 `RuntimeError("AUTH_PROVIDER_NOT_CONFIGURED")`
- 整型变量无法解析或非正 → `ValueError`，错误信息包含变量名
- `local_session_secret` 为空 → `ValueError`
- 任何路径都不打印密钥

**不引入新依赖**：使用标准库 `os.environ`，不引入 `pydantic-settings`。

## 5. D4 收紧 `auth_mode="disabled"`

`auth_mode="disabled"` 是绕过认证的旁路，必须与 `auth_mode="local"` 的 `session/local` 端点同级限定：**仅当请求来源为回环地址时才生效**，否则抛 `AccessError("PERMISSION_DENIED")`。

- 复用 `routes/session.py` 已有的回环集合判断 `{"127.0.0.1", "::1"}`
- 测试影响：`AsgiClient` 的 `client` 为 `("127.0.0.1", 123)`，故现有集成测试**不受影响**

## 6. 错误与安全边界

- 对外错误码**零变更**
- 租约过短不损坏数据（§2.5），但会浪费解析；默认值取保守的长租约
- 日志与异常消息中不得出现 `local_session_secret`
- 回收动作沿用既有删除守卫，**不新增任何删除路径**
- 本切片不引入新的文件读取范围

## 7. 验证方式

硬约束：**不新增测试文件或测试用例，只扩展既有测试的断言**。

| 目标 | 扩展位置 |
|---|---|
| 租约重认领 + 重跑收敛到 `READY_FOR_REVIEW` | `tests/integration/test_lifecycle.py::test_execution_failure_and_cleanup_failure_are_durable_diagnostics` |
| `Settings` 与 Alembic 共用同一环境变量 | `tests/integration/test_sqlite_repository.py`（该文件已用 `HW_REVIEW_DATABASE_URL` 驱动 alembic） |
| 启动回收已接入（死代码消除） | `tests/integration/test_task_api.py` 的 `client` fixture 覆盖路径 |
| `disabled` 回环收紧后回环来源仍放行 | `tests/integration/test_task_api.py` 现有 `client` |

另需**真实 HTTP 运行态验证**（非内存 ASGI），与既有 `docs/evidence/` 惯例一致。

## 8. 明确不做

- 不改 `_NEXT`、不新增前向迁移、不改审核规则与判定语义
- 不做启动期强制回收（方案 A）
- 不处理多 worker / 生产数据库并发（属 S3）
- **不新增前端"重新执行"入口** —— 需要先定 UI 语义（自动重试 vs 手动按钮、是否展示剩余租约），列为紧随其后的独立切片 S1e
- 不做任何 Git 操作

## 9. 遗留缺口（必须在交付说明中显式声明）

本切片使**服务端具备恢复能力**（租约到期后 `POST /api/tasks/{id}/execute` 可成功重跑），但 UI 目前**没有任何触发 `execute` 的入口**（`TaskDetailView` 只轮询 `GET`）。因此在 S1e 完成前：

- 用户仍会看到任务停留在中间态并持续轮询
- 恢复必须通过 API 手工触发

**S1 单独完成不构成"用户可见的缺陷修复"**，不得据此宣称该可用性风险已关闭。
