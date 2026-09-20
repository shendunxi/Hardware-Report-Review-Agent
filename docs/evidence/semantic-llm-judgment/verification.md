# 语义规则大模型判定验证（2026-09-20）

## 1. 决策与口径

| 项 | 值 |
|---|---|
| 决策人 | 用户 |
| 覆盖范围 | **所有检查项**（`HW_REVIEW_LLM_SCOPE=all`，默认）——任务冻结快照里每个启用的检查项都发送给模型 |
| 数据外发口径 | **发送整份归一化报告**（用户 2026-09-20 明确选择） |
| 端点 | `https://sgp-ai-platforms.skyworth-cloud.cn/v1`（OpenAI 兼容，集团企业云） |
| 模型 | `deepseek-v4-flash`（推理模型） |
| 默认开关 | `HW_REVIEW_LLM_ENABLED=false`，**默认不出网** |

外发内容的逐项清单见 [`data-egress-statement.md`](data-egress-statement.md)（OQ-06 答复材料）。

## 2. 合并策略：模型只决定引擎决定不了的事（双向保护）

`EvaluationService._apply_llm_judgement` 的三条分支：

| 引擎结论 | 模型结论 | 最终 | 说明 |
|---|---|---|---|
| `NEEDS_REVIEW` | 任意 | **模型结论** | 引擎弃权，模型作答；`engine_version` 记为模型 |
| 确定结论 | **相同** | 引擎结论 | 保留引擎的 `basis_code` 与明细代码（客观规则的审计骨架），并入模型的证据；`engine_version` 记为 `引擎+模型` |
| `NON_COMPLIANT` | 更宽松 | **保留 `NON_COMPLIANT`** | 不得清除硬失败（PRD：缺少必需外部证据时系统初判不符合） |
| 其他确定结论 | 不同 | **`NEEDS_REVIEW`** | 升级人工，依据码 `LLM_DISAGREES_WITH_ENGINE` |

**为什么两个方向都要保护**：`NON_COMPLIANT` 与 `COMPLIANT` 都**不会**强制人工复核
（只有 `NEEDS_REVIEW` 会）。所以模型**既不能凭空清除一个不符合项，也不能凭空造出一个**——
两种情况都只会静默通过。分歧一律升级为人工确认。

**分歧永不静默丢弃**：两种分歧分支都把引擎结论与模型结论一并写入 `unresolved_semantics`。

### 合并策略矩阵（12 条用例，failures: 0）

用桩 judge 直接驱动 `_apply_llm_judgement`，不联网、不依赖真实文档：

| 引擎 | 模型 | 最终 | 依据码 |
|---|---|---|---|
| `COMPLIANT` | `COMPLIANT` | `COMPLIANT` | 引擎原码保留 |
| `COMPLIANT` | `NON_COMPLIANT` | `NEEDS_REVIEW` | `LLM_DISAGREES_WITH_ENGINE` |
| `COMPLIANT` | `NEEDS_REVIEW` | `NEEDS_REVIEW` | `LLM_DISAGREES_WITH_ENGINE` |
| `COMPLIANT` | `NOT_APPLICABLE` | `NEEDS_REVIEW` | `LLM_DISAGREES_WITH_ENGINE` |
| `NON_COMPLIANT` | `COMPLIANT` | `NON_COMPLIANT` | `ROLLUP_HARD_FAILURE` 保留 |
| `NON_COMPLIANT` | `NEEDS_REVIEW` | `NON_COMPLIANT` | `ROLLUP_HARD_FAILURE` 保留 |
| `NON_COMPLIANT` | `NON_COMPLIANT` | `NON_COMPLIANT` | 引擎原码保留 |
| `NOT_APPLICABLE` | `COMPLIANT` | `NEEDS_REVIEW` | `LLM_DISAGREES_WITH_ENGINE` |
| `NOT_APPLICABLE` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | 引擎原码保留 |
| `NEEDS_REVIEW` | `COMPLIANT` | `COMPLIANT` | `LLM_*` |
| `NEEDS_REVIEW` | `NON_COMPLIANT` | `NON_COMPLIANT` | `LLM_*` |
| `NEEDS_REVIEW` | `NOT_APPLICABLE` | `NOT_APPLICABLE` | `LLM_*` |

另验证：6 条分歧用例全部把双方结论写入 `unresolved_semantics`；模型作答时
`engine_version = stub-judge-1`，一致时 `engine_version = a11-engine-1+stub-judge-1`。

## 3. 响应契约校验（16 条降级路径 + 4 条应放行路径，failures: 0）

不联网，用桩替换 HTTP opener：

| 注入 | 结果 |
|---|---|
| 传输错误 | `LLM_CALL_FAILED` |
| 响应体非 JSON / 信封缺 `choices` | `LLM_RESPONSE_UNPARSEABLE` |
| `content` 为空（思维链吃光 `max_tokens`） | `LLM_EMPTY_CONTENT` |
| `content` 是散文 | `LLM_RESPONSE_UNPARSEABLE` |
| `content` 是对象而非数组 | `LLM_CONTRACT_VIOLATION` |
| 规则缺失 / 返回未知规则 | `LLM_RULE_SET_MISMATCH` |
| 非法 `status` 值 | `LLM_INVALID_STATUS` |
| 证据行号越界 | `LLM_EVIDENCE_OUT_OF_RANGE` |
| `COMPLIANT` 无证据 | `LLM_UNSUPPORTED_VERDICT` |
| `NON_COMPLIANT` 既无证据也无缺失材料 | `LLM_UNSUPPORTED_VERDICT` |
| `evidence_lines` 为字符串 | `LLM_CONTRACT_VIOLATION` |
| `basis_text` / `basis_code` 为空 | `LLM_CONTRACT_VIOLATION` |
| 证据行数超上限 | `LLM_INPUT_TOO_LARGE`（**不截断**） |
| `COMPLIANT` + 真证据行 | 放行 |
| `NON_COMPLIANT` + 仅缺失材料 | 放行 |
| `NOT_APPLICABLE` 无证据 | 放行 |
| JSON 被 ` ```json ` 包裹 | 放行（去围栏后解析） |

**16 条降级路径全部落到 `NEEDS_REVIEW`，没有一条变成「符合」。**

## 4. 真实端到端（真实样本 + 真实端点）

样本 `TCY30 PP项目硬件测试报告(xPON)-V1.32.xls`（6,978,048 B），21 条启用规则全部送模型。

### 4.1 模型行为符合「绝不臆造」

引擎判为 `NEEDS_REVIEW` 的项，模型**主动拒绝判定**并给出缺失材料：

| 规则 | 模型判定 | 引用证据（真实存在） | 缺失材料 |
|---|---|---|---|
| TR-08 首页填写 | `NEEDS_REVIEW` | `sheet:首页/cell:A1 硬件测试报告`、`A2 产品型号`、`E2 TCY30` | `必填字段清单` |
| TR-16 结论重点及顺序 | `NEEDS_REVIEW` | `cell:A26 序号`、`C26 本次测试结论`、`K26 缺陷等级` | `问题清单`、`排序依据` |

### 4.2 判定值未被凭空改变

两次运行的合并结果：

| | 第 1 次 | 第 2 次 |
|---|---|---|
| 耗时 | 66.7 s | 73.2 s |
| 模型结论被采纳 | 3 | 3 |
| 硬失败保留（模型更宽松） | 未触发 | 未触发 |
| 分歧升级人工 | 未触发 | 未触发 |
| **因引擎硬失败而保留 `NON_COMPLIANT`** | 18 | 18 |

即：21 项中 18 项是引擎的确定性硬失败，模型没有也不能改动；其余 3 项由引擎弃权、模型作答。
**两次运行均未出现「模型更宽松」或「模型分歧」的情况**，因此保护的触发路径由第 2 节的
桩矩阵证明，不由真实运行证明。

### 4.3 ⚠️ 模型结论在两次相同输入下不一致

| 规则 | 第 1 次 | 第 2 次 |
|---|---|---|
| TR-09 测试用例选择 | `NON_COMPLIANT`（缺对应表） | `NEEDS_REVIEW`（缺对应表） |
| TR-08 首页填写 | 引用 **57** 个证据位置 | 引用 **0** 个证据位置 |

`temperature=0` 也未能消除（推理模型的思维链本身有随机性）。这不是代码差异——其余变量受控。

**含义**：

1. 同一任务重跑可能给出不同初判 → **既有的「按修订冻结」机制是必须的**，不是可选项。
2. 边界规则上模型不稳定 → 人工复核兜底是唯一可靠做法。
3. 这也是第 2 节双向保护存在的理由：模型抖动既可能清除也可能凭空造出不符合项。

### 4.4 证据位置上限

第 1 次运行中 TR-04 返回 **265** 个、TR-22 返回 **182** 个证据位置（模型把它读过的行都列上）。
已加上限 50，并在 `basis_text` 中显式注明省略数量，沿用清单导出既有的「去重 + 限 50 + 注明省略」做法。

> 第 2 次运行没有任何规则触及上限，因此该上限逻辑**未被真实运行执行到**；它是针对第 1 次
> 观测到的问题加的，逻辑本身是简单的切片。

## 5. 默认关闭下的回归

`HW_REVIEW_LLM_ENABLED` 未设置时：

- 后端全量：**313 passed / 6 skipped / 0 failed**，与接入前完全一致。
- `_semantic_judge(settings)` 返回 `None`，不构造适配器，**不发起任何网络请求**。

## 6. 未关闭项

- **OQ-06 尚未签署**：见 [`data-egress-statement.md`](data-egress-statement.md)。
  签署前不应在生产启用。
- **对端留存政策未知**，需端点归属方书面说明。
- **模型结论不可复现**（§4.3），已知并接受；结果按修订冻结。
- 单个任务全部检查项共用一次调用；模型漏答某条则降级 `NEEDS_REVIEW`，无重试。
- 并发 `C=5` 下的 P95 未测量；单次调用实测 66–73 s。
- 未做 OCR；扫描型 PDF 不适用本切片。
- 未接入企业微信身份认证；当前仍是回环可用的本地签名 Cookie 会话。

## 7. 文档同步状态

| 文档 | 状态 |
|---|---|
| 本文件 | 已同步 `scope=all` 与双向保护 |
| [`data-egress-statement.md`](data-egress-statement.md) | 新增（OQ-06 签署材料） |
| `docs/superpowers/specs/2026-09-20-semantic-llm-judgment-design.md` | ✅ 已同步（§1 范围、§3 挂载点与合并策略、§6 `llm_scope`、§8 验证、§10 未关闭项） |
| `docs/superpowers/plans/2026-09-20-semantic-llm-judgment.md` | ✅ 已同步（Task 1 / 6 / 8） |
| `README.md` | ✅ 已同步（配置表补 `llm_scope`；「只补位不覆盖」改为双向保护） |
