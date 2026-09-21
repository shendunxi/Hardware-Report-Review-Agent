# 工程债清理验证（2026-09-21）

八项，全部不依赖任何外部输入。**代码行为对外无变化**（除两处刻意收紧的启动校验），
目标是消除「同一规则有多份实现」「失败时留下半成品状态」「问题只在运行时才暴露」这三类隐患。

**回归基线**：`313 passed / 6 skipped / 0 failed`（改前改后一致）。

---

## 1. `@app.on_event` → `lifespan`

`create_app` 原先用 `@app.on_event("shutdown")` 关闭共享 SQLAlchemy engine。该 API 在
FastAPI 中已弃用。改为 `FastAPI(lifespan=_lifespan(bundle))`，`finally` 中关闭 engine，
真实服务器与进程内 ASGI 传输都会触发。

**证据**：全量回归的告警数从 **98 降到 32**，其中消失的正是 FastAPI 的
`on_event is deprecated` 告警。剩余 32 条全部来自 alembic 的 `path_separator` 弃用提示，
与本次改动无关。

**刻意未改**：启动期的 `ensure_baseline()`、工作区回收、中断执行巡检仍留在 `create_app`
同步执行。它们是被测试直接断言的确定性行为（`app.state.startup_reclamation`），
搬进 lifespan 只会让「建 app」与「起服务」的时机变得不确定。

## 2. 配置启动自检

新增 `config.self_check(settings)`，由 `create_app` 调用：**不通过抛异常拒绝启动**，
通过但可疑写日志告警。新增 `environment` 字段（`development` 默认 / `production`）。

| 情形 | development | production |
|---|---|---|
| `auth_mode` 不是 `local` / `disabled` | **拒绝启动** | **拒绝启动** |
| `database_url` / `storage_root` 是相对路径 | 告警 | **拒绝启动** |
| `local_session_secret` 为默认值或 < 32 字符 | 告警 | **拒绝启动** |
| `auth_mode=disabled` | 允许 | **拒绝启动** |
| 语义判定未启用 | 告警 | 同左 |

原先 `create_app` 内联的 `RuntimeError("AUTH_PROVIDER_NOT_CONFIGURED")` 并入本自检
（异常类型统一为 `ValueError`；仓库与测试中无人捕获该异常类型）。

**为什么区分环境**：相对路径默认值让「从 `backend/` 启动 uvicorn」直接可用，是开发期的
便利；但「相对当前工作目录」在正式部署里是隐患。`production` 拒绝它，而不是告警。

**已验证 10 项**（桩设置，不启服务）：

```
OK  dev 默认值不阻塞启动                    OK  production + 默认相对路径 -> 拒绝
OK  dev 默认值给出弱密钥告警                OK  production + auth_mode=disabled -> 拒绝
OK  dev 默认值给出相对路径告警              OK  production + 弱密钥 -> 拒绝
OK  dev 默认值提示语义判定关闭              OK  未知 auth_mode -> 拒绝
OK  production + 绝对路径 + 强密钥 -> 放行   OK  绝对 sqlite URL 不被误判为相对
```

> 相对 URL 判定同时覆盖 `sqlite:///./x`、`sqlite:///x`（相对）与
> `sqlite:////x`、`sqlite:///C:/x`（绝对），以及非 sqlite 的服务式 URL（永不告警）。

## 3. API 层不再穿透 `service._bundle`

`GET /api/tasks` 原先直接用 `service._bundle.{sources,failures,results,decisions,revisions}`
和 `service._bundle.tasks.list_recent()` 拼装响应，绕过了服务层。

新增 `LifecycleService.list_summary()`，并把子记录的读取顺序抽成 `_task_records(task)`，
由 `detail()` 与 `list_summary()` 共用 —— 顺带消除了 `GET /api/tasks/{id}` 与此端点之间
重复的子记录拼装。

**已验证**：`list_summary()[0]` 与 `detail(task_id)` 的键集合完全一致
（`manual_decisions` / `revisions` / `rule_results` / `source_files` / `stage_failures` / `task`）；
空库返回 `()`；`create()` 后立刻可见。

## 4. 任务创建的部分写入

原先 `create()` 逐个 `sources.create(...)` 落库：

```
tasks.create(task)                    ← 任务已落库
for each file: sources.create(source) ← 逐个写入，中途失败即留下子集
```

失败时任务处于 `FAILED` 且**指向它自己上传文件的一个子集** —— 后续任何按「任务的全部源文件」
做的判断都会被这个子集欺骗。

现在改为 `SqliteSourceFileRepository.create_all()`：**整个源文件集合一个事务写入**。
`StageError` 与 `RepositoryError` 分别落到 `STAGING` / `SOURCE_COMMIT_FAILED` 并标记任务失败。

**刻意保留**：任务行仍先写入。因为 `_fail()` 需要更新已存在的任务行才能记录失败诊断
（`stage_failures.task_id` 是指向 `tasks` 的外键），完全原子化会让「上传失败」这件事
既无任务也无诊断记录，只剩一个 400 响应。

**已验证原子性**（这是本项的核心断言）：

```
OK  重复主键 -> 抛 RepositoryConflictError
OK    失败后一行也未落库（原子）      ← 关键：不是「部分成功」
OK  成功时整批落库
OK  空集合是空操作
```

## 5. 三处重复实现收敛

| 重复 | 原状 | 现状 |
|---|---|---|
| 时间戳 UTC 归一化 | **5 份**：`models.py` 三份（`_template_utc_datetime` / `_review_utc_datetime` / `_utc_datetime`）+ `repositories.py` 两份（`_utc_text` / `_utc_datetime`） | `domain/timestamps.py`：`as_utc` / `as_utc_optional` / `as_stored_text` / `from_stored_text` |
| A1 单元格地址 | **2 份**：`parsers/base.a1_address`、`models._a1_address` | `domain/addressing.py`：`a1_address`，两处均改为引用 |
| 证据类型校验 | **2 份**完全相同的 `validate_evidence_kinds` | `models._validate_evidence_kinds(role, kinds)`，两个模型各调一次 |

`repositories.py` 中 31 个调用点改为引用共享实现（`as_stored_text` ×17、`from_stored_text` ×14）。

**顺带发现一处已经漂移**：`models._a1_address` **没有负数校验**，而 `parsers/base.a1_address` 有。
两份实现已经开始分叉。当前无行为差异（`TableCell.row` / `column` 都是 `Field(ge=0)`，
负数在校验前已被拒绝），但收敛后由 `TableCell` 反查地址的那条不变量才有意义 ——
「模型自己算出的地址」与「解析器写入的地址」现在必然同源。

## 6. 规则引擎启动期自检

`A11Engine.evaluate_rule` 用 `getattr(self, f"_rule_{rule_id[3:]}")` 按名字解析处理器。
原先「注册表启用了某条规则但没有对应处理器」只会在**任务跑到评估阶段**才抛
`AttributeError` —— 那时上传已被接受。

现在 `A11Engine.__init__` 断言注册表与处理器**一一对应**，两个方向都查：

| 情形 | 结果 |
|---|---|
| 真实注册表与处理器一一对应 | 构造成功 |
| 启用规则缺处理器（注入 `TR-99`） | 构造失败：`enabled A11 rules have no evaluation handler: TR-99 (_rule_99)` |
| 处理器无对应启用规则（注入 `_rule_05`） | 构造失败：`A11 evaluation handlers have no enabled rule: _rule_05` |

反向检查顺带覆盖「给 `TR-05`（`DISABLED`）写了处理器」这种永远不会执行的代码。
错误信息以**规则 ID 在前**，因为那才是注册表与检查表使用的标识。

## 7. `frontend/dist` 缺失不再静默降级

原先：

```python
static_root = vue_root if (vue_root / "index.html").is_file() else prototype_root
if static_root.is_dir():
    app.mount("/", ...)
```

`frontend/dist` 是构建产物且**已在 `.gitignore` 中**，所以全新克隆必然没有它 —— 此时会**静默**
改为服务 `prototype/a11-ui`。运维无法从任何输出察觉「现在服务的不是真实应用」，也无法察觉
两边都不存在时 `/` 会 404。

现在由 `_select_frontend_root()` 决定并记录：

| 情形 | 返回 | 日志 |
|---|---|---|
| `frontend/dist/index.html` 存在 | `("vue")` | 无 |
| 不存在，但 `prototype/a11-ui/index.html` 存在 | `("prototype")` | **WARNING**，含 `npm run build` 提示 |
| 两者都没有 | `(None, "none")` | **ERROR**，说明 API 可用但 `/` 会 404 |
| 两者都没有 | 不执行 mount | — |

选择结果同时暴露为 `app.state.frontend_root` / `app.state.frontend_source`，便于测试与运维核对。

> 注意：本机 `frontend/dist` 已构建，所以 `test_static_frontend.py` 走的是 vue 分支。
> 本次改动**不改变**该测试的结果，只是让另外两条分支从「静默」变为「有声」。

## 8. 依赖版本上下界

原先 13 个运行时依赖中 7 个完全没有约束（`fastapi`、`uvicorn`、`alembic`、
`python-multipart`、`xlrd`、`olefile`、`pymupdf`、`pywin32`、`psutil`），
一次上游破坏性发布即可让环境不可复现。

| 依赖 | 新约束 | 本机已装 |
|---|---|---|
| `fastapi` | `>=0.115,<1` | 0.141.1 |
| `uvicorn` | `>=0.30,<1` | 0.53.0 |
| `pydantic` | `>=2.7,<3` | 2.13.5 |
| `sqlalchemy` | `>=2.0,<3` | 2.0.54 |
| `alembic` | `>=1.13,<2` | 1.20.0 |
| `python-multipart` | `>=0.0.9,<1` | 0.0.32 |
| `xlrd` | `>=2.0,<3` | 2.0.2 |
| `openpyxl` | `>=3.1,<4`（原有） | 3.1.5 |
| `xlutils` | `>=2,<3`（原有） | 2.0.0 |
| `olefile` | `>=0.47,<1` | 0.47 |
| `pymupdf` | `>=1.24,<2` | 1.28.2 |
| `pywin32` | `>=306,<400` | 312 |
| `psutil` | `>=5.9,<8` | 7.2.2 |
| `pytest`（test） | `>=8,<10` | 9.1.1 |
| `xlwt`（test） | `>=1.3,<2` | 1.3.0 |

**所有下界都不高于本机已装版本**，因此不影响现有环境；`<n` 上界挡住下一个主版本。

---

## 未做的事（有意）

- **未给验证脚本留下测试用例**。沿用本项目「不新增测试文件或测试用例、只扩展既有断言」
  的约束，上述 32 项验证是一次性脚本，验证后已删除。
  代价：**这些断言不在回归中**，日后改动可能悄悄破坏它们而不被察觉。
  需要的话下一步应把它们固化为测试。
- **未处理** `%TEMP%` ACL、WPS 宿主策略、语义判定的 OQ-06 —— 分别属宿主环境、
  外部输入与合规签署，不是工程债。
- **未改** 生产数据库选型、多 worker 租约实测、企业微信身份认证 —— 均依赖外部决策。
