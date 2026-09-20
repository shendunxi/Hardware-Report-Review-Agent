# 运行可靠性与配置外部化 —— 验证证据

日期：2026-09-20
切片：S1（对应 `docs/superpowers/specs/2026-09-20-runtime-reliability-and-configuration-design.md`）
验证方式：RED→GREEN 单元/集成断言 + 隔离环境下的真实 HTTP 运行态验证

## 1. 结论

| 缺陷 | 结论 | 关键证据 |
|---|---|---|
| D1 中间态任务永久卡死 | **GO** | RED 复现 `assert 'PARSING' == 'READY_FOR_REVIEW'`；租约到期后真实 HTTP 重认领收敛到 `READY_FOR_REVIEW`（21 项） |
| D2 `clean_expired` 死代码 | **GO** | 启动期回收已接入；隔离环境中植入的过期工作区在启动时被删除 |
| D3 迁移库与运行时库可能不一致 | **GO** | `get_settings()` 读取 `HW_REVIEW_DATABASE_URL`，与 `migrations/env.py` 同源；运行态验证全程由环境变量驱动 |
| D4 `disabled` 模式无来源限制 | **GO（ASGI 层验证）** | 注入 `client.host = 10.0.0.7` → HTTP 403 `PERMISSION_DENIED`；回环来源仍放行 |

**本切片不关闭用户可见的可用性风险。** 服务端已具备恢复能力，但 UI 仍无触发 `execute` 的入口（见 §6）。

## 2. 回归证据

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `python -m pytest -q --basetemp=.tmp\pytest-s1-full` | **311 passed, 8 skipped** |
| 改动前基线 | 同上 | 311 passed, 8 skipped（**数量一致**：仅扩展断言，未新增用例） |
| 受影响文件聚焦 | `pytest tests/integration/test_lifecycle.py test_task_api.py test_sqlite_repository.py` | **58 passed** |
| 静态检查 | IDE 诊断（6 个改动源文件） | 0 问题 |

> 说明：本机 pytest 默认临时根目录 ACL 损坏，必须使用 `--basetemp`（沿用仓库既有 `.tmp\pytest-*` 约定）。

## 3. D1 RED → GREEN

### RED（临时把 `claim_execution` 的守卫回退为 `state == 'CREATED'`）

```
>       assert recovered["state"] == "READY_FOR_REVIEW"
E       AssertionError: assert 'PARSING' == 'READY_FOR_REVIEW'
E         - READY_FOR_REVIEW
E         + PARSING
tests\integration\test_lifecycle.py:143: AssertionError
FAILED tests/integration/test_lifecycle.py::test_execution_failure_and_cleanup_failure_are_durable_diagnostics
1 failed
```

这正是缺陷本身：任务在 `PARSING` 永久停留。恢复守卫后同一断言 GREEN（`1 passed`）。

### 断言覆盖的行为

扩展 `test_lifecycle.py::test_execution_failure_and_cleanup_failure_are_durable_diagnostics`：

1. 认领但不执行 → `request_execution(...)[1] is True`
2. 模拟进程死亡：手工置 `PARSING`，`updated_at` 保持新鲜
3. **租约未到期不可认领**：`request_execution(...)[1] is False`，状态仍为 `PARSING`
4. `inspect_interrupted()` 恰好报告一条 `PARSING`
5. 把 `updated_at` 回拨 `execution_lease_seconds + 60`
6. `POST /execute` → 收敛到 `READY_FOR_REVIEW`，21 条结果且 `rule_id` 互不重复
7. 恢复后 `inspect_interrupted() == []`

## 4. 真实 HTTP 运行态验证

为避免污染开发库，运行态验证使用**完全由环境变量供给**的隔离库与存储根，端口 `8767`。

环境变量（同时构成 D3 的端到端证明）：

```
HW_REVIEW_DATABASE_URL=sqlite:///backend/.tmp/s1-runtime/runtime.db
HW_REVIEW_STORAGE_ROOT=backend/.tmp/s1-runtime/storage
HW_REVIEW_AUTH_MODE=local
HW_REVIEW_EXECUTION_LEASE_SECONDS=90
HW_REVIEW_WORKSPACE_TTL_SECONDS=3600
```

结果摘录（本次验证脚本与产物位于临时工作区 `backend/.tmp/`，已按约定清理）：

```json
{
  "get_root_status": 200,
  "sweep": { "reclaimed_logged": false, "workspace_removed": true },
  "first_execute": { "http": 202, "state": "FILES_STAGED" },
  "after_first_execute": { "state": "READY_FOR_REVIEW", "results": 21 },
  "after_simulated_death": { "state": "PARSING" },
  "startup_report": {
    "warning_logged": true,
    "line": "task f084fe8a-aa85-4c06-b14f-1705f26e5159 interrupted in PARSING; reclaimable in 59s",
    "state_unchanged": true
  },
  "execute_while_lease_held": { "http": 202, "state": "PARSING" },
  "execute_after_lease_expiry": { "http": 202, "state": "FILES_STAGED" },
  "recovered": { "state": "READY_FOR_REVIEW", "results": 21, "distinct_rules": 21 },
  "lease_reclaim_succeeded": true
}
```

逐项解读：

| 观察 | 含义 |
|---|---|
| `sweep.workspace_removed == true` | 启动回收真实生效：植入的 3 天前孤儿工作区在启动时被删除 |
| `startup_report.warning_logged == true` | 中断任务被上报，含剩余可认领秒数 **59s**（= 90s 租约 − 已过 30s），与配置一致 |
| `startup_report.state_unchanged == true` | 启动**未**静默改写任务状态（§2.6 设计约束） |
| `execute_while_lease_held.state == "PARSING"` | 租约未到期时不重复执行（防双跑） |
| `execute_after_lease_expiry.state == "FILES_STAGED"` | 租约到期后成功重认领 |
| `recovered.state == "READY_FOR_REVIEW"`，21 项且无重复 | 重跑收敛，幂等（§2.5） |

**已知观测限制**：`sweep.reclaimed_logged == false`。回收成功计数使用 `_LOGGER.info`，而 Uvicorn 默认把根日志级别设为 `WARNING`，故该行默认不可见（同一次运行中 `WARNING` 级的中断上报正常输出）。权威机器可读记录是 `app.state.startup_reclamation`。**这是运维可见性缺口，不是功能缺陷**，需在部署时把应用日志级别调到 INFO。

## 5. D4 验证与其边界

`auth_mode=disabled` 的回环限定通过 ASGI 层验证，因为该层可直接注入任意 `client.host`：

扩展 `test_lifecycle.py::test_validation_errors_use_the_frozen_error_envelope`：

```python
denied = client.request("GET", "/api/tasks", client_host="10.0.0.7")
assert denied.status_code == 403
assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
```

同一机制下，`test_task_api.py` 的既有 `client` fixture（`client.host = 127.0.0.1`）仍全部通过，证明回环来源未被误拒。

### 真实 HTTP 侧为何无法取反例（已实测）

尝试把服务绑定到 `127.0.0.2` 并连接该地址，期望得到 403，实测为 200。访问日志给出了原因：

```
[s1-loopback-127_0_0_2.log]
INFO:     127.0.0.1:52830 - "GET /api/tasks HTTP/1.1" 200 OK
```

即使目标地址是 `127.0.0.2`，服务端观察到的客户端仍是 `127.0.0.1`（内核为回环连接选择回环源地址）。因此：

- 该探测**不构成反例**，只是无法构造非可信来源
- 同时说明受信集合 `{127.0.0.1, ::1}` 对 IPv4 回环客户端**并不偏严**

**未采用的做法**：把服务绑定到 `0.0.0.0` 或某个局域网接口以取得真实非回环对端。这会让一个 `auth_mode=disabled`（无认证、全角色）的服务在局域网可达，属于不必要的暴露风险，因此刻意不做。D4 的结论以 ASGI 层验证为准。

## 6. 遗留缺口（必须显式声明）

**S1 不构成用户可见的缺陷修复。**

- 服务端恢复能力已具备：租约到期后 `POST /api/tasks/{id}/execute` 可以成功重跑
- 但前端**没有任何触发 `execute` 的入口**：`TaskDetailView` 只轮询 `GET /api/tasks/{id}`，`CreateTaskView` 仅在创建时调用一次
- 因此用户仍会看到任务停留在中间态并持续轮询，恢复必须由 API 手工触发

该缺口需要独立切片 **S1e**，且需先定 UI 语义：自动重试 vs 手动「重新执行」按钮、是否展示剩余租约时间、租约未到期时按钮如何呈现。

## 7. 未验证与既有限制

- 多 worker / 多实例部署下的租约竞争未验证（本机为单进程 Uvicorn）；生产数据库与并发属 S3
- 租约默认值 1800s 必须大于最长单次评估耗时；该约束当前由 DOC 转换超时（1200s）推导，一旦调整解析超时必须同步复核
- `updated_at` 以 ISO 文本比较实现租约时钟，依赖全部写入路径统一走 `_utc_text`（与既有 `order_by(created_at)` 同一前提）
- `auth_mode="disabled"` 仅用于测试与本地调试；生产身份提供方仍未接入，生产认证门禁保持 **NO-GO**
- 未执行真实浏览器人工验收
