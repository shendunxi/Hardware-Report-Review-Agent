# 语义规则大模型判定实施计划（S5）

依据：[`../specs/2026-09-20-semantic-llm-judgment-design.md`](../specs/2026-09-20-semantic-llm-judgment-design.md)

约束：不新增测试文件或测试用例，只扩展既有断言；不引入第三方 HTTP 依赖。

## Task 1: 配置与授权开关

**Files:** `src/hw_review/config.py`

- [x] 新增 `llm_enabled`（默认 `false`）、`llm_base_url`、`llm_api_key`、`llm_model`、
      `llm_timeout_seconds`、`llm_max_tokens`、`llm_max_evidence_lines`、
      `llm_scope`（默认 `all`，用户 2026-09-20 选择）。
- [x] 新增严格的布尔解析 `_flag`，非法值启动即失败。
- [x] `ENABLED=true` 而 `BASE_URL`/`API_KEY`/`MODEL` 任一为空 → 启动即失败，不静默降级。
- [x] 默认关闭时**不发起任何出网请求**，对齐 PRD「未获授权时外发 0 次」。

## Task 2: 端口

**Files:** `src/hw_review/domain/ports.py`

- [x] 新增 `runtime_checkable` 的 `SemanticJudge` 协议，`judge(request) -> JudgeOutcome`。
- [x] 协议文档明确：实现**不得**因单条规则失败而抛异常，必须降级为 `NEEDS_REVIEW`。

## Task 3: 证据行扁平化

**Files:** `src/hw_review/services/semantic_judge.py`

- [x] `build_judge_request(rules, sources)`：把 `ReportDocument` 扁平化为编号证据行，
      并建立 `行号 -> EvidenceLocator` 的本地映射。
- [x] 只外发文本：不含源文件路径、不含任务/模板标识、不含二进制。
- [x] 逐行**不重复**发送结构地址（模型只用行号引用，地址仅本地映射用）。

## Task 4: OpenAI 兼容适配器

**Files:** `src/hw_review/services/semantic_judge.py`

- [x] 用标准库 `urllib.request` 实现 `/chat/completions` POST，`temperature=0`。
- [x] `PROMPT_VERSION` 常量，`engine_version = openai-compat-<model>-<prompt>`。
- [x] 提示词要求：只能引用行号；不得臆造外部标准；不确定即 `NEEDS_REVIEW`；
      只输出 JSON 数组且每规则恰好一项。

## Task 5: 响应校验（全部失败路径降级）

**Files:** `src/hw_review/services/semantic_judge.py`

- [x] 实现设计文档第 5 节的全部 `LLM_*` 判定码。
- [x] `COMPLIANT` / `NON_COMPLIANT` 必须有证据行（或缺失材料），否则拒绝。
- [x] 证据 `content_hash` 一律本地计算，不采信模型给出的任何哈希或地址。
- [x] 证据行数超上限 → `LLM_INPUT_TOO_LARGE`，**不截断**。

## Task 6: 接入评估编排

**Files:** `src/hw_review/services/evaluation.py`

- [x] `EvaluationService(..., judge=None, llm_scope="all")`。
- [x] `scope=all` 发送全部启用检查项；`scope=semantic_only` 仅补位引擎弃权的规则。
- [x] **引擎已确定的结论永不被移动（双向保护）**：引擎 `NON_COMPLIANT` 时模型不得放宽；
      其余确定结论若与模型不一致则升级为 `NEEDS_REVIEW` + `LLM_DISAGREES_WITH_ENGINE`，
      双方结论写入 `unresolved_semantics`。
- [x] 引擎 `NEEDS_REVIEW` 时才由模型作答；一致时保留引擎依据码与明细代码并并入模型证据，
      `engine_version` 记为 `引擎+模型`。
- [x] 模型抛异常时任务不失败，保留引擎原结果。
- [x] 单条规则证据位置上限 `MAX_EVIDENCE_LOCATORS = 50`，超出时在 `basis_text` 注明省略数量。

## Task 7: 应用装配

**Files:** `src/hw_review/api/app.py`

- [x] `_semantic_judge(settings)`：未授权返回 `None`；启用时装配并在启动日志中
      **显式警告报告文本将外发**。

## Task 8: 验证

- [x] 默认关闭下全量后端回归：**313 passed / 6 skipped / 0 failed**
      （双向保护加入后复测仍为 313 / 6）。
- [x] 真实端到端（真实样本 + 真实端点）跑了**两次**：21 项，66.7 s / 73.2 s；
      18 项引擎硬失败全部保留，3 项由引擎弃权、模型作答，证据地址可核验。
      ⚠️ 两次判定不同，`temperature=0` 未能消除（推理模型思维链本身有随机性）。
- [x] 故障注入矩阵：16 条降级路径全部落到 `NEEDS_REVIEW`，4 条合法路径不被误降级，0 失败。
- [x] 合并策略矩阵：12 种引擎 × 模型组合，0 失败；两种分歧分支均记录双方结论。
- [x] 证据记录：`docs/evidence/semantic-llm-judgment/verification.md`；
      OQ-06 签署材料：`docs/evidence/semantic-llm-judgment/data-egress-statement.md`。
- [x] 文档同步：spec 的 `scope=all` 与双向保护、本计划的 Task 1/6/8、README。
