# 中断执行可重试入口 —— 验证证据（S1e）

日期：2026-09-20
切片：S1e（对应 `docs/superpowers/specs/2026-09-20-interrupted-execution-retry-design.md`）
目标：闭合 S1 遗留缺口 —— 服务端已能重跑中断执行，但 UI 无触发入口

## 1. 结论

| 目标 | 结论 | 证据 |
|---|---|---|
| 可重试性由服务端唯一派生 | **GO** | `LifecycleService.execution_status` 成为唯一实现；`inspect_interrupted` 改为复用它 |
| 载荷字段随租约正确翻转 | **GO** | 真实 HTTP：租约内 `false`/剩余 74s → 过期后 `true`/0 |
| 列表与详情一致 | **GO** | `GET /api/tasks` 同样携带 `execution` |
| 重试真正收敛 | **GO** | `POST /execute` → 202 → 轮询落定 `READY_FOR_REVIEW`，21 项结果，`execution` 回到 `null` |
| store action 复用既有端点 | **GO** | 前端测试断言 `reexecute` 调用 `/api/tasks/t1/execute` 后重载 |
| 视图渲染 | **未自动化覆盖** | 见 §5，必须人工浏览器确认 |

## 2. 契约

任务载荷新增派生字段（服务端计算，前端不复算租约语义）：

```ts
execution: { reclaimable: boolean; seconds_until_reclaimable: number } | null
```

| 值 | 含义 |
|---|---|
| `null` | 不在被中断的中间态（正常流转或已到终态） |
| `{reclaimable: false, seconds_until_reclaimable: N}` | 处于 `{FILES_STAGED, PARSING, PARSED, EVALUATING}`，租约未到期，还有 N 秒 |
| `{reclaimable: true, seconds_until_reclaimable: 0}` | 租约已到期，`POST /execute` 会真正启动执行 |

该字段由 `_task_payload` 统一注入，因此**创建 / 执行 / 列表 / 详情 / 完成 / 重开**六个端点全部一致（7 处调用点已全部更新）。

## 3. 回归

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `python -m pytest -q --basetemp=.tmp\pytest-s1e-full` | **311 passed, 8 skipped** |
| 后端聚焦 | `pytest tests/integration/test_lifecycle.py` | **9 passed** |
| 前端测试 | `npm test -- --run` | **8 files / 17 tests passed** |
| 前端类型检查 | `npm run typecheck` | 通过（无输出） |
| 前端生产构建 | `npm run build` | 通过；`TaskDetailView` 2.63 kB → **3.42 kB** |
| 构建产物文案 | `Select-String dist/assets/*.js` | `执行已中断` / `重新执行` / `上次执行被中断` / `需等待执行租约到期` 均 FOUND 于 `TaskDetailView-CO6WdcjJ.js` |
| 改动前基线 | 同上前两项 | 311 passed / 8 skipped、17 passed（**数量一致**：仅扩展断言，未新增用例） |

## 4. 真实 HTTP 验证

隔离实例（端口 8769、独立库与存储根、`HW_REVIEW_EXECUTION_LEASE_SECONDS=90`），开发库与存储未被触碰：

```json
{
  "healthy_task":       { "state": "READY_FOR_REVIEW", "execution": null },
  "lease_held":         { "state": "PARSING", "execution": { "reclaimable": false, "seconds_until_reclaimable": 74 } },
  "list_carries_field": { "reclaimable": false, "seconds_until_reclaimable": 74 },
  "after_lease_expiry": { "state": "PARSING", "execution": { "reclaimable": true, "seconds_until_reclaimable": 0 } },
  "retry":              { "http": 202, "state": "READY_FOR_REVIEW", "execution": null, "results": 21 },
  "passed": true
}
```

逐项解读：

| 观察 | 含义 |
|---|---|
| `lease_held.seconds_until_reclaimable == 74` | 租约 90s − 已过 15s ≈ 75s，与配置吻合，说明剩余时间是**真算出来的** |
| `after_lease_expiry.reclaimable == true` 且剩余为 `0` | 越过租约后按钮应变为可用 |
| `retry.http == 202` 且最终 `READY_FOR_REVIEW` / 21 项 | 重试路径真实生效，结果集完整且无重复 |
| `retry.execution == null` | 恢复后面板应自动消失 |

### 过程中发现并修正的自身错误

验证脚本最初在 `POST /execute` 之后**立即** `GET` 并断言已到 `READY_FOR_REVIEW`，实测拿到的是 `PARSING` / `PARSED`。原因是：**真实 HTTP 下执行是异步的** —— 接口先返回 `202`，后台任务在响应之后才跑完（ASGI 内存客户端里这一时序被同步吃掉，所以集成测试看不到该差异）。

修正方式是在脚本里轮询到状态落定。这同时确认了一条重要事实：**UI 的 2 秒轮询正是处理这一时序的机制**，因此视图不需要自己等待，只需在 `execution` 字段变化时改变按钮状态。

## 5. 缺口与未验证（必须随交付说明）

1. **视图层没有自动化测试。** 仓库没有 `TaskDetailView` 的 spec，而本切片沿用「不新增测试文件/用例」的约束，因此不可能为它补测试。已验证的是：`vue-tsc` 通过、生产构建通过、构建产物包含全部面板文案、`store.reexecute` 有断言覆盖。
   **这不足以宣称视图已验收**，必须由人工在浏览器中确认：
   - 以「测试报告审核」打开一个处于中间态且租约已到期的任务详情页 → 应看到「执行已中断」面板且「重新执行」按钮可用
   - 租约未到期时 → 按钮禁用，并显示「约 X 分钟」提示
   - 点击后 → 任务离开中间态，面板消失
2. **崩溃是模拟的**：通过直接改库把任务置为中间态，不是真实进程崩溃。真实崩溃路径本身由 S1 的租约机制覆盖（见 `docs/evidence/runtime-reliability/verification.md`）。
3. **最坏等待时间未改善**：租约默认 1800s，用户在最坏情况下需等待一个完整租约周期才能点击重试。缩短等待需要更细粒度心跳或更短租约，属后续议题。
4. 未做自动重试（刻意设计，理由见 spec §2.1）。
5. 未执行真实浏览器人工验收；未做任何 Git 操作。
