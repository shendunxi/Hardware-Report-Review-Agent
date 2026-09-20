"""Semantic rule judgement through an authorized OpenAI-compatible chat endpoint.

Design constraints that shape this module:

* The report is sent as **numbered evidence lines** derived from the normalized
  document. The model may only cite line numbers, and those numbers are mapped
  back to real ``EvidenceLocator`` values locally. A citation therefore cannot be
  fabricated: an out-of-range line index invalidates the verdict, and the hash on
  every locator is computed here rather than trusted from the response.
* No provider failure may ever surface as compliance. Every failure path degrades
  the affected rules to ``NEEDS_REVIEW`` with a stable ``LLM_*`` basis code.
* Evidence is never truncated. An oversized request degrades instead, because a
  silently shortened report would make the verdict unverifiable.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Literal
from uuid import UUID

from pydantic import Field

from hw_review.domain.enums import ReviewStatus
from hw_review.domain.models import DomainModel, EvidenceLocator, ReviewSource, TemplateRule


PROMPT_VERSION = "prompt1"

JUDGEABLE_JUDGEMENTS = frozenset({"AI", "RULE_PLUS_AI"})
_PERMITTED_STATUSES = frozenset(
    {
        ReviewStatus.COMPLIANT,
        ReviewStatus.NON_COMPLIANT,
        ReviewStatus.NOT_APPLICABLE,
        ReviewStatus.NEEDS_REVIEW,
    }
)
_VERDICTS_REQUIRING_EVIDENCE = frozenset(
    {ReviewStatus.COMPLIANT, ReviewStatus.NON_COMPLIANT}
)

# Stable basis codes. Every one of them means "the automated semantic attempt did
# not produce a verifiable verdict", never "compliant".
CODE_INPUT_TOO_LARGE = "LLM_INPUT_TOO_LARGE"
CODE_CALL_FAILED = "LLM_CALL_FAILED"
CODE_RESPONSE_UNPARSEABLE = "LLM_RESPONSE_UNPARSEABLE"
CODE_EMPTY_CONTENT = "LLM_EMPTY_CONTENT"
CODE_CONTRACT_VIOLATION = "LLM_CONTRACT_VIOLATION"
CODE_RULE_SET_MISMATCH = "LLM_RULE_SET_MISMATCH"
CODE_INVALID_STATUS = "LLM_INVALID_STATUS"
CODE_EVIDENCE_OUT_OF_RANGE = "LLM_EVIDENCE_OUT_OF_RANGE"
CODE_UNSUPPORTED_VERDICT = "LLM_UNSUPPORTED_VERDICT"


class EvidenceLine(DomainModel):
    """One citable line of normalized report text."""

    index: int = Field(ge=1)
    source_name: str
    container: str
    structural_address: str
    text: str = Field(min_length=1)


class RuleJudgementRequest(DomainModel):
    """The part of a frozen template rule the model is allowed to see."""

    rule_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    verifiable_requirement: str = Field(min_length=1)
    required_materials: str = Field(min_length=1)
    confirmed_boundary: str = Field(min_length=1)


class JudgeRequest(DomainModel):
    rules: tuple[RuleJudgementRequest, ...]
    lines: tuple[EvidenceLine, ...]
    locators: dict[int, EvidenceLocator]


class RuleJudgement(DomainModel):
    """One rule's outcome, either from the model or from a local degradation."""

    rule_id: str = Field(min_length=1)
    initial_status: ReviewStatus
    basis_code: str = Field(min_length=1)
    basis_text: str = Field(min_length=1)
    evidence_locators: tuple[EvidenceLocator, ...] = ()
    missing_materials: tuple[str, ...] = ()
    unresolved_semantics: tuple[str, ...] = ()


class JudgeOutcome(DomainModel):
    """Exactly one judgement per requested rule."""

    judgements: tuple[RuleJudgement, ...]


def build_judge_request(
    rules: tuple[TemplateRule, ...], sources: tuple[ReviewSource, ...]
) -> JudgeRequest:
    """Flatten the normalized documents into numbered, locally-mapped evidence lines.

    Only text is sent: no source path, no task or template identifier, no binary.
    """

    lines: list[EvidenceLine] = []
    locators: dict[int, EvidenceLocator] = {}
    for source in sources:
        source_name = source.source_file.original_name
        for container in source.document.containers:
            container_label = f"{container.kind}:{container.name_or_number}"
            for block in container.blocks:
                if block.kind == "text" and block.text and block.text.strip():
                    index = len(lines) + 1
                    lines.append(
                        EvidenceLine(
                            index=index,
                            source_name=source_name,
                            container=container_label,
                            structural_address=block.structural_address,
                            text=block.text.strip(),
                        )
                    )
                    locators[index] = EvidenceLocator(
                        source_file_id=source.source_file.id,
                        container=container_label,
                        structural_address=block.structural_address,
                        bbox=block.bbox,
                        quoted_text=block.text.strip(),
                        content_hash=block.content_hash,
                    )
                elif block.kind == "table":
                    for cell in block.cells:
                        if not cell.display_value or not cell.display_value.strip():
                            continue
                        index = len(lines) + 1
                        lines.append(
                            EvidenceLine(
                                index=index,
                                source_name=source_name,
                                container=container_label,
                                structural_address=cell.structural_address,
                                text=cell.display_value.strip(),
                            )
                        )
                        locators[index] = EvidenceLocator(
                            source_file_id=source.source_file.id,
                            container=container_label,
                            structural_address=cell.structural_address,
                            bbox=block.bbox,
                            quoted_text=cell.display_value.strip(),
                            content_hash=cell.content_hash,
                        )
    return JudgeRequest(
        rules=tuple(
            RuleJudgementRequest(
                rule_id=rule.rule_id,
                summary=rule.summary,
                verifiable_requirement=rule.verifiable_requirement,
                required_materials=rule.required_materials,
                confirmed_boundary=rule.confirmed_boundary,
            )
            for rule in rules
        ),
        lines=tuple(lines),
        locators=locators,
    )


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()


_SYSTEM_PROMPT = """你是硬件测试报告审核助手。你会收到一份归一化报告的编号证据行，以及若干待判定规则。
对每条规则给出判定，并**只**用证据行号引用你实际读到的内容。

硬性要求：
1. 只能使用允许的判定值：COMPLIANT（符合）、NON_COMPLIANT（不符合）、NOT_APPLICABLE（不适用）、NEEDS_REVIEW（待人工确认）。
2. 判 COMPLIANT 或 NON_COMPLIANT 时，必须至少引用一个证据行号。判 NON_COMPLIANT 也可以改
   为给出 missing_materials（缺失材料）。引用不存在的行号会导致该条判定作废。
3. 不要臆造任何外部标准、命名规则、排序规则、期望值或字段清单。若规则依赖的判据或材料
   未在证据中出现，判 NEEDS_REVIEW，并把原因写进 unresolved_semantics。
4. 不确定就判 NEEDS_REVIEW。宁可交给人工，也不要给出没有证据支撑的结论。
5. 只输出一个 JSON 数组，不要输出解释、不要用 markdown 代码块包裹。数组必须为**每一条**
   待判定规则恰好给出一项，格式如下：
[
  {
    "rule_id": "TR-17",
    "status": "NON_COMPLIANT",
    "basis_code": "简短英文大写下划线代号",
    "basis_text": "一句话中文结论",
    "evidence_lines": [12, 34],
    "missing_materials": [],
    "unresolved_semantics": []
  }
]
"""


def _render_user_prompt(request: JudgeRequest) -> str:
    rules = "\n".join(
        f"- rule_id: {rule.rule_id}\n"
        f"  校验要点: {rule.summary}\n"
        f"  可验证要求: {rule.verifiable_requirement}\n"
        f"  所需材料: {rule.required_materials}\n"
        f"  已确认边界: {rule.confirmed_boundary}"
        for rule in request.rules
    )
    # The structural address is deliberately NOT repeated per line: the model only
    # cites line numbers and the address is mapped back locally. Emitting it here
    # would add roughly 35 characters per line for no benefit.
    chunks: list[str] = []
    current_header: str | None = None
    for line in request.lines:
        header = f"{line.source_name} · {line.container}"
        if header != current_header:
            chunks.append(f"\n### {header}")
            current_header = header
        chunks.append(f"[{line.index}] {line.text}")
    return (
        f"【待判定规则（共 {len(request.rules)} 条，每条都必须返回一项）】\n{rules}\n\n"
        f"【证据行（共 {len(request.lines)} 行，只能引用这里的行号）】"
        + "\n".join(chunks)
    )


_Opener = Callable[[urllib.request.Request, float], object]


def _default_opener(request: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout)


class OpenAiCompatSemanticJudge:
    """Judge semantic rules through an OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 180,
        max_tokens: int = 4096,
        max_evidence_lines: int = 12_000,
        opener: _Opener | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip() or not api_key.strip():
            raise ValueError(
                "semantic judge requires base_url, model and api_key"
            )
        self._endpoint = f"{base_url.strip().rstrip('/')}/chat/completions"
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._max_evidence_lines = max_evidence_lines
        self._opener = opener or _default_opener
        self.engine_version = f"openai-compat-{self._model}-{PROMPT_VERSION}"

    # ------------------------------------------------------------------ public

    def judge(self, request: JudgeRequest) -> JudgeOutcome:
        if not request.rules:
            return JudgeOutcome(judgements=())
        if len(request.lines) > self._max_evidence_lines:
            return self._degrade_all(
                request,
                CODE_INPUT_TOO_LARGE,
                f"证据行数 {len(request.lines)} 超过上限 {self._max_evidence_lines}；"
                "为保证可核验未做截断，本批语义规则转人工确认",
            )
        try:
            body = self._fetch(request)
        except Exception as error:  # noqa: BLE001 - any transport fault is one outcome
            return self._degrade_all(
                request,
                CODE_CALL_FAILED,
                f"语义判定调用失败：{type(error).__name__}: {error}",
            )
        try:
            envelope = json.loads(body)
            content = envelope["choices"][0]["message"]["content"]
        except (TypeError, ValueError, KeyError, IndexError):
            return self._degrade_all(
                request, CODE_RESPONSE_UNPARSEABLE, "无法解析供应商响应信封"
            )
        if not isinstance(content, str) or not content.strip():
            return self._degrade_all(
                request,
                CODE_EMPTY_CONTENT,
                "模型返回了空 content；推理模型的思维链可能已耗尽 max_tokens",
            )
        try:
            payload = json.loads(_strip_fences(content))
        except (TypeError, ValueError):
            return self._degrade_all(
                request, CODE_RESPONSE_UNPARSEABLE, "模型输出不是合法 JSON 数组"
            )
        if not isinstance(payload, list):
            return self._degrade_all(
                request, CODE_CONTRACT_VIOLATION, "模型输出不是 JSON 数组"
            )
        return self._interpret(request, payload)

    # ----------------------------------------------------------------- internal

    def _fetch(self, request: JudgeRequest) -> str:
        body = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _render_user_prompt(request)},
            ],
        }
        http_request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        with self._opener(http_request, self._timeout_seconds) as response:
            return response.read().decode("utf-8")

    def _degrade_all(
        self, request: JudgeRequest, code: str, message: str
    ) -> JudgeOutcome:
        return JudgeOutcome(
            judgements=tuple(
                RuleJudgement(
                    rule_id=rule.rule_id,
                    initial_status=ReviewStatus.NEEDS_REVIEW,
                    basis_code=code,
                    basis_text=message,
                    unresolved_semantics=(message,),
                )
                for rule in request.rules
            )
        )

    def _interpret(self, request: JudgeRequest, payload: list) -> JudgeOutcome:
        requested = {rule.rule_id for rule in request.rules}
        seen: dict[str, dict] = {}
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("rule_id"), str):
                continue
            seen[item["rule_id"]] = item
        if set(seen) != requested:
            missing = sorted(requested - set(seen))
            extra = sorted(set(seen) - requested)
            return self._degrade_all(
                request,
                CODE_RULE_SET_MISMATCH,
                f"模型返回的规则集合与请求不一致；缺失={missing or '无'} 多余={extra or '无'}",
            )

        judgements: list[RuleJudgement] = []
        for rule in request.rules:
            item = seen[rule.rule_id]
            raw_status = item.get("status")
            try:
                status = ReviewStatus(raw_status)
            except ValueError:
                judgements.append(
                    self._degrade_one(
                        rule.rule_id,
                        CODE_INVALID_STATUS,
                        f"模型返回了不允许的判定值：{raw_status!r}",
                    )
                )
                continue
            if status not in _PERMITTED_STATUSES:
                judgements.append(
                    self._degrade_one(
                        rule.rule_id,
                        CODE_INVALID_STATUS,
                        f"模型返回了不允许的判定值：{raw_status!r}",
                    )
                )
                continue

            raw_lines = item.get("evidence_lines") or []
            if not isinstance(raw_lines, list) or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in raw_lines
            ):
                judgements.append(
                    self._degrade_one(
                        rule.rule_id,
                        CODE_CONTRACT_VIOLATION,
                        "evidence_lines 必须是整数数组",
                    )
                )
                continue
            out_of_range = sorted(
                {value for value in raw_lines if value not in request.locators}
            )
            if out_of_range:
                judgements.append(
                    self._degrade_one(
                        rule.rule_id,
                        CODE_EVIDENCE_OUT_OF_RANGE,
                        f"模型引用了不存在的证据行号：{out_of_range[:10]}",
                    )
                )
                continue

            missing_materials = _string_tuple(item.get("missing_materials"))
            evidence = tuple(
                request.locators[value] for value in sorted(set(raw_lines))
            )
            if status in _VERDICTS_REQUIRING_EVIDENCE and not evidence and not (
                status is ReviewStatus.NON_COMPLIANT and missing_materials
            ):
                judgements.append(
                    self._degrade_one(
                        rule.rule_id,
                        CODE_UNSUPPORTED_VERDICT,
                        f"模型判 {status.value} 但未提供任何证据行或缺失材料",
                    )
                )
                continue

            basis_text = item.get("basis_text")
            if not isinstance(basis_text, str) or not basis_text.strip():
                judgements.append(
                    self._degrade_one(
                        rule.rule_id, CODE_CONTRACT_VIOLATION, "basis_text 缺失或为空"
                    )
                )
                continue
            basis_code = item.get("basis_code")
            if not isinstance(basis_code, str) or not basis_code.strip():
                judgements.append(
                    self._degrade_one(
                        rule.rule_id, CODE_CONTRACT_VIOLATION, "basis_code 缺失或为空"
                    )
                )
                continue

            judgements.append(
                RuleJudgement(
                    rule_id=rule.rule_id,
                    initial_status=status,
                    basis_code=f"LLM_{basis_code.strip().upper()[:60]}",
                    basis_text=basis_text.strip(),
                    evidence_locators=evidence,
                    missing_materials=missing_materials,
                    unresolved_semantics=_string_tuple(item.get("unresolved_semantics")),
                )
            )
        return JudgeOutcome(judgements=tuple(judgements))

    @staticmethod
    def _degrade_one(rule_id: str, code: str, message: str) -> RuleJudgement:
        return RuleJudgement(
            rule_id=rule_id,
            initial_status=ReviewStatus.NEEDS_REVIEW,
            basis_code=code,
            basis_text=message,
            unresolved_semantics=(message,),
        )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


__all__ = [
    "EvidenceLine",
    "JudgeOutcome",
    "JudgeRequest",
    "OpenAiCompatSemanticJudge",
    "PROMPT_VERSION",
    "RuleJudgement",
    "RuleJudgementRequest",
    "build_judge_request",
]
