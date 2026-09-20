# 语义规则大模型判定设计（S5）

状态：**已实施**（2026-09-20）。实施中用户把覆盖范围从「仅语义规则」扩大为「全部检查项」，
并追加「模型不得移动引擎已确定结论」的双向保护；本文件已同步这两处变更。
实测结果见 [`docs/evidence/semantic-llm-judgment/verification.md`](../../evidence/semantic-llm-judgment/verification.md)。

## 1. 目标与边界

把任务冻结快照中**每个启用的检查项**交给获授权大模型，使其得到「带可核验证据的判定」。

设计时原计划只覆盖 **13 条语义规则**（`main_judgment` 为 `RULE_PLUS_AI` 或 `AI`：
TR-02/03/06/08/12/13/14/15/16/17/18/22）从「一律 `NEEDS_REVIEW`」升级为
「由获授权大模型给出带可核验证据的判定」。实施中用户已于 2026-09-20 把范围扩大为
`scope=all`（**全部 21 个启用项**），并追加「引擎已确定的结论不被模型移动」的双向保护
（完整策略见 §3 挂载点）。

### 非目标

- 不改客观规则（`RULE`）的判定逻辑。
- 不改判定词汇：系统初判仍只有 `COMPLIANT` / `NON_COMPLIANT` / `NOT_APPLICABLE` / `NEEDS_REVIEW`。
- 不改状态机、模板版本规则、导出格式、数据库结构。
- 不引入第三方 HTTP 依赖；不新增测试文件或测试用例（沿用「只扩展既有断言」的约束）。
- 不执行 OCR。

## 2. 实测事实（设计依据）

2026-09-20 在本机对冻结样本实测归一化文本规模：

| 样本 | 格式 | 归一化字符数 | 解析耗时 |
|---|---|---:|---:|
| S-01（源文件 14.7 MB） | XLS | **82,713** | 0.3 s |
| S-09 | XLS | 61,516 | 0.4 s |
| S-17 | XLS | 57,763 | 0.3 s |
| S-13 | PDF | 16,587 | 1.5 s |
| S-14 | DOC | 16,727 | 35.5 s |

14.7 MB 的 XLS 归一化后只有 8.3 万字符（6,356 个非空片段）。因此
**「每个任务一次调用、送整份归一化报告」是可行且便宜的**：约 5 万输入 token，
按供应商 `$0.15 / 1M` 输入计价约 **$0.008 / 任务**。这一口径由用户明确选择（「发送报告」）。

供应商实测特征（`deepseek-v4-flash` @ `https://sgp-ai-platforms.skyworth-cloud.cn/v1`，
企业内网云）：

- 是**推理模型**：响应含 `reasoning_content`（思维链）与 `content`（答案）两个字段。
- `max_tokens` 偏小时**思维链会把预算吃光**，`content` 返回空字符串且 `finish_reason="length"`
  （实测 `max_tokens=10` 时复现）。
- 端点为 OpenAI 兼容的 `/chat/completions`。
- 属集团企业云，报告内容不出企业边界。

## 3. 架构

新增端口 + 适配器，`EvaluationService` 只依赖端口：

```
domain/ports.py            SemanticJudge (Protocol)
services/semantic_judge.py OpenAiCompatSemanticJudge（stdlib urllib.request）
                           JudgeRequest / RuleJudgementRequest / RuleJudgement（Pydantic）
services/evaluation.py     仅对语义规则调用 judge，失败即降级
api/app.py                 依据 Settings 装配（未启用则不装配）
```

### 挂载点

`EvaluationService.evaluate` 中，冻结 A11 实现的结果生成后，由 `_apply_llm_judgement` 处理：

| 项 | `scope=all`（默认） | `scope=semantic_only` |
|---|---|---|
| 发送对象 | 全部启用检查项 | 仅引擎判为 `NEEDS_REVIEW` 且 `main_judgment` 属 `JUDGEABLE_JUDGEMENTS` 的规则 |

**合并策略——模型只决定引擎决定不了的事：**

| 引擎结论 | 模型结论 | 最终 | 依据码 |
|---|---|---|---|
| `NEEDS_REVIEW` | 任意 | 模型结论 | `LLM_*` |
| 确定 | 相同 | 引擎结论（保留引擎 `basis_code` 与明细代码，并入模型证据） | 引擎原码 |
| `NON_COMPLIANT` | 更宽松 | **保留 `NON_COMPLIANT`** | 引擎原码 |
| 其他确定 | 不同 | **`NEEDS_REVIEW`** | `LLM_DISAGREES_WITH_ENGINE` |

**为什么两个方向都要保护**：`NON_COMPLIANT` 与 `COMPLIANT` 都**不会**强制人工复核
（只有 `NEEDS_REVIEW` 会）。因此模型既不能凭空清除一个硬失败，也不能凭空造出一个——
两种情况都只会静默通过。分歧一律升级人工，且双方结论都写入 `unresolved_semantics`，
不静默丢弃。

`engine_version` 在模型作答时记为模型版本，一致时记为 `引擎+模型`；分歧时为 `引擎+模型`，
以便从任一条结果反查该次判定同时经过了两侧。

## 4. 外发内容

**只送归一化文本的证据行，不送原文件、不送本机路径、不送任务/模板标识。**

证据行由 `ReportDocument` 扁平化而来，每行一个非空文本块或一个非空表格单元格：

```
[n] <display text>
```

`n` 是行序号，与 `(source_file_id, container, structural_address, content_hash, quoted_text)`
的映射在本地保存。提示词要求模型**只以行号引用证据**，从而：

- 外发体积最小（`[123] ` 前缀约 5 字符，不重复送地址）；
- 引用可被**精确、确定性地**解析回 `EvidenceLocator`，无需模糊文本匹配；
- 模型若引用不存在的行号，可立即判定为无效。

提示词版本以常量固化（`PROMPT_VERSION`），并写入 `engine_version`
（形如 `openai-compat-deepseek-v4-flash-prompt1`），使每条结果都能追溯到模型与提示词。

## 5. 响应契约与校验

要求模型返回 JSON 数组，每项：

```json
{
  "rule_id": "TR-17",
  "status": "NON_COMPLIANT",
  "basis_code": "...",
  "basis_text": "...",
  "evidence_lines": [123, 456],
  "missing_materials": [],
  "unresolved_semantics": []
}
```

### 全部校验失败路径一律降级为该规则的 `NEEDS_REVIEW`

| 情形 | basis_code |
|---|---|
| 网络错误 / HTTP 非 2xx / 超时 | `LLM_CALL_FAILED` |
| 响应体不是合法 JSON | `LLM_RESPONSE_UNPARSEABLE` |
| `content` 为空（含「思维链吃光预算」） | `LLM_EMPTY_CONTENT` |
| 结构不符契约（缺字段 / 类型错） | `LLM_CONTRACT_VIOLATION` |
| 返回了未请求的 `rule_id`、重复、或漏返回 | `LLM_RULE_SET_MISMATCH` |
| `status` 不在允许集合内 | `LLM_INVALID_STATUS` |
| `evidence_lines` 含越界行号 | `LLM_EVIDENCE_OUT_OF_RANGE` |
| 判 `COMPLIANT` / `NON_COMPLIANT` 却无任何证据行 | `LLM_UNSUPPORTED_VERDICT` |
| 输入证据行数超过配置上限 | `LLM_INPUT_TOO_LARGE`（**不截断**） |

**永不**把校验失败当作「无意见 → 符合」。判 `COMPLIANT` 必须有证据行，这是 G5 的落点，
也直接实现「虚构证据位置为 0」。

## 6. 配置

| 键 | 默认 | 说明 |
|---|---|---|
| `HW_REVIEW_LLM_ENABLED` | `false` | **默认关闭**。关闭时完全不发起网络请求，对齐 PRD「未获授权时外发 0 次」 |
| `HW_REVIEW_LLM_BASE_URL` | 空 | OpenAI 兼容基址，如 `https://…/v1` |
| `HW_REVIEW_LLM_API_KEY` | 空 | 密钥；仅从环境变量读取，**不入库、不入仓** |
| `HW_REVIEW_LLM_MODEL` | 空 | 如 `deepseek-v4-flash` |
| `HW_REVIEW_LLM_TIMEOUT_SECONDS` | `180` | 单次调用超时 |
| `HW_REVIEW_LLM_MAX_TOKENS` | `4096` | 必须足够容纳思维链，见第 2 节 |
| `HW_REVIEW_LLM_MAX_EVIDENCE_LINES` | `12000` | 超过则整批降级，**不截断** |
| `HW_REVIEW_LLM_SCOPE` | `all` | `all` = 全部启用检查项（**用户 2026-09-20 选择**）；`semantic_only` = 只补位引擎弃权的规则 |

单条规则的证据位置另有上限 `MAX_EVIDENCE_LOCATORS = 50`：超出时收录前 50 条，并在
`basis_text` 中显式注明省略数量（沿用清单导出既有的「去重 + 限 50 + 注明省略」做法）。
该上限由第 1 次真实运行观测到模型返回 265 个位置后加入。

启用状态校验：`ENABLED=true` 而 `BASE_URL`/`MODEL`/`API_KEY` 任一为空 → 启动即失败，
不静默降级。

## 7. 确定性与可追溯

- 调用参数固定 `temperature = 0`。
- **不声称大模型结果可复现**：同一输入重跑可能得到不同判定。因此
  - 结果按既有修订机制**冻结**（`review_revisions`），历史不可变；
  - `engine_version` 含模型与提示词版本，`basis_code` 使用 `LLM_*` 前缀；
  - 证据只有通过本地行号→`EvidenceLocator` 映射才能落地，且 `content_hash` 由本地计算，
    **不采信模型给出的任何哈希或地址**。
- 客观规则（`RULE`）的确定性不受影响。

## 8. 验证方式

- **默认关闭**：全量后端回归必须仍为 313 passed / 6 skipped，且不产生任何出网请求。
  ✅ 已达成（313 passed / 6 skipped）
- **启用后**：用真实样本创建任务，确认检查项得到 `LLM_*` 或引擎保留结果、
  `evidence_locators` 非空且地址存在于文档中；确认硬失败未被改写。
  ✅ 已达成（21 项中 18 项引擎硬失败全部保留）
- **降级路径**：以本地假 judge 与真实故障注入（错误模型名、超小 `max_tokens`）
  验证第 5 节表格中每条路径都落到 `NEEDS_REVIEW`。
  ✅ 16 条降级路径 + 4 条应放行路径，failures: 0
- **合并策略**：以桩 judge 直接驱动 `_apply_llm_judgement`，覆盖引擎 × 模型的全部
  12 种组合，并断言两种分歧分支都记录双方结论。✅ failures: 0
- **不新增测试文件或测试用例**，只扩展既有断言（上述矩阵与故障注入为一次性验证脚本，
  验证后已删除，未留在仓库）。

## 9. 交付物

- 新增：`domain/ports.py` 的 `SemanticJudge`；`services/semantic_judge.py`；本 spec；
  `docs/superpowers/plans/2026-09-20-semantic-llm-judgment.md`；
  `docs/evidence/semantic-llm-judgment/verification.md`
- 修改：`config.py`、`services/evaluation.py`、`api/app.py`、README
- 不做：数据库结构变更、导出格式变更、`RULE` 规则判定变更、Git 之外的外部系统接入

## 10. 未关闭项

- PRD **OQ-06** 要求「信息安全负责人 + 产品负责人」正式签署数据外发范围与留存方式。
  本设计按用户 2026-09-20 的口径实现（发送整份归一化报告），**合规签署仍待补齐**。
  可签署材料见 [`data-egress-statement.md`](../../evidence/semantic-llm-judgment/data-egress-statement.md)；
  **对端留存政策仍未知**，需端点归属方书面说明。
- **模型结论不可复现**：实测同一输入两次运行给出不同判定（见验证文档 §4.3）。用户已接受，
  由「按修订冻结」+ 人工兜底。
- **报告文件名会被外发**：TR-07 的判定对象本身包含文件名，属判定所需信息。
- 单个任务的全部检查项共用一次调用；若模型漏答某条，该条降级为 `NEEDS_REVIEW`，
  无重试。是否需要按规则重试属后续优化。
- 证据位置上限 50 是针对第 1 次真实运行的问题后加的，**第 2 次运行未触及该路径**。
- 并发 `C=5` 下的 P95 未测量；单次调用实测 66–73 s。
- 数据库、导出格式、`RULE` 规则判定均未变更。
