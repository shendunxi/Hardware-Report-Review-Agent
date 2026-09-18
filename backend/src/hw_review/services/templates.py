"""Read-only XLS validation and persisted template lifecycle operations."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import xlrd
from pydantic import ValidationError

from hw_review.domain import (
    TemplateRule,
    TemplateStatus,
    TemplateValidationFinding,
    TemplateVersion,
)
from hw_review.persistence import (
    RepositoryBundle,
    RepositoryConflictError,
    RepositoryNotFoundError,
)
from hw_review.rules import A11Registry


TEMPLATE_NAME = "硬件测试过程检查单"
CHECKLIST_SHEET = "硬件测试过程检查表"


class TemplateServiceError(Exception):
    """Stable template-management failure exposed by the API boundary."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class TemplateValidationResult:
    matched_source_rows: int
    findings: tuple[TemplateValidationFinding, ...]


class A11TemplateValidator:
    """Validate an A11-derived workbook without writing to it."""

    def validate(self, path: Path, *, expected_version: str) -> TemplateValidationResult:
        findings: list[TemplateValidationFinding] = []
        try:
            workbook = xlrd.open_workbook(path, formatting_info=True, on_demand=False)
        except (OSError, xlrd.XLRDError) as error:
            return TemplateValidationResult(
                matched_source_rows=0,
                findings=(
                    self._finding(
                        "TEMPLATE_UNREADABLE",
                        "ERROR",
                        f"模板无法读取：{error}",
                    ),
                ),
            )

        matching = [name for name in workbook.sheet_names() if name == CHECKLIST_SHEET]
        if not matching:
            return TemplateValidationResult(
                matched_source_rows=0,
                findings=(
                    self._finding(
                        "CHECKLIST_SHEET_MISSING",
                        "ERROR",
                        f"缺少工作表“{CHECKLIST_SHEET}”。",
                    ),
                ),
            )
        if len(matching) != 1:
            findings.append(
                self._finding(
                    "CHECKLIST_SHEET_DUPLICATE",
                    "ERROR",
                    f"工作表“{CHECKLIST_SHEET}”必须且只能存在一个。",
                )
            )
        sheet = workbook.sheet_by_name(CHECKLIST_SHEET)
        actual_version = str(sheet.cell_value(1, 0)).strip() if sheet.nrows > 1 else ""
        if actual_version == "A111" or expected_version.strip() == "A111":
            findings.append(
                self._finding(
                    "INVALID_A111_VERSION",
                    "ERROR",
                    "A111 是历史笔误，不能作为模板版本。",
                    f"{CHECKLIST_SHEET}!A2",
                )
            )
        elif not actual_version:
            findings.append(
                self._finding(
                    "TEMPLATE_VERSION_MISSING",
                    "ERROR",
                    "模板版本不能为空。",
                    f"{CHECKLIST_SHEET}!A2",
                )
            )
        elif actual_version != expected_version.strip():
            findings.append(
                self._finding(
                    "TEMPLATE_VERSION_MISMATCH",
                    "ERROR",
                    f"工作表版本 {actual_version} 与目标版本 {expected_version.strip()} 不一致。",
                    f"{CHECKLIST_SHEET}!A2",
                )
            )
        if sheet.ncols < 7:
            findings.append(
                self._finding(
                    "RESULT_COLUMNS_MISSING",
                    "ERROR",
                    "模板必须包含 D、E、F、G 四个结果列。",
                    f"{CHECKLIST_SHEET}!D:G",
                )
            )

        matched = 0
        for definition in A11Registry.source_rows():
            row_index = definition.source_row - 1
            if row_index >= sheet.nrows:
                findings.append(
                    self._finding(
                        "SOURCE_ROW_MISSING",
                        "ERROR",
                        f"缺少来源行 {definition.source_row}（{definition.id}）。",
                        f"{CHECKLIST_SHEET}!A{definition.source_row}",
                    )
                )
                continue
            raw_sequence = sheet.cell_value(row_index, 1)
            try:
                sequence = int(float(raw_sequence))
            except (TypeError, ValueError):
                sequence = -1
            if sequence != definition.source_sequence:
                findings.append(
                    self._finding(
                        "SOURCE_SEQUENCE_MISMATCH",
                        "ERROR",
                        f"来源行 {definition.source_row} 的序号应为 {definition.source_sequence}。",
                        f"{CHECKLIST_SHEET}!B{definition.source_row}",
                    )
                )
            else:
                matched += 1

        semantic_count = sum(
            definition.main_judgment in {"AI", "RULE_PLUS_AI"}
            for definition in A11Registry.executed_rules()
        )
        findings.append(
            self._finding(
                "SEMANTIC_REVIEW_CONFIGURATION_REQUIRED",
                "WARNING",
                f"{semantic_count} 个执行项涉及语义判断；未配置获授权模型时将进入待人工确认。",
            )
        )
        return TemplateValidationResult(matched_source_rows=matched, findings=tuple(findings))

    @staticmethod
    def _finding(
        code: str,
        severity: str,
        message: str,
        structural_address: str | None = None,
    ) -> TemplateValidationFinding:
        return TemplateValidationFinding(
            code=code,
            severity=severity,
            message=message,
            structural_address=structural_address,
        )


class TemplateService:
    """Own managed copies and enforce the draft/publish/retire lifecycle."""

    def __init__(
        self,
        bundle: RepositoryBundle,
        *,
        template_root: Path,
        baseline_path: Path,
        validator: A11TemplateValidator | None = None,
    ) -> None:
        self._bundle = bundle
        self._template_root = Path(template_root)
        self._baseline_path = Path(baseline_path)
        self._validator = validator or A11TemplateValidator()

    def ensure_baseline(self) -> TemplateVersion:
        existing = self._bundle.templates.find_by_name_version(TEMPLATE_NAME, "A11")
        if existing is not None:
            return existing
        validation = self._validator.validate(self._baseline_path, expected_version="A11")
        errors = tuple(item for item in validation.findings if item.severity == "ERROR")
        if errors:
            raise TemplateServiceError(
                "BASELINE_TEMPLATE_INVALID",
                "内置 A11 模板结构无效。",
                {"findings": [item.model_dump(mode="json") for item in errors]},
            )
        now = datetime.now(timezone.utc)
        template_id = uuid5(NAMESPACE_URL, "hardware-review-template:A11")
        stat = self._baseline_path.stat()
        template = TemplateVersion(
            id=template_id,
            name=TEMPLATE_NAME,
            version="A11",
            status=TemplateStatus.PUBLISHED,
            source_filename=self._baseline_path.name,
            source_path=self._baseline_path,
            source_sha256=self._digest(self._baseline_path),
            source_size_bytes=stat.st_size,
            source_mtime_ns=stat.st_mtime_ns,
            source_rows=validation.matched_source_rows,
            effective_rules=len(A11Registry.executed_rules()),
            validation_findings=validation.findings,
            created_by="系统基线",
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        try:
            return self._bundle.templates.create(
                template, self._baseline_rules(template_id, now)
            )
        except RepositoryConflictError:
            found = self._bundle.templates.find_by_name_version(TEMPLATE_NAME, "A11")
            if found is None:
                raise
            return found

    def upload(
        self,
        source_path: Path,
        *,
        original_name: str,
        name: str,
        version: str,
        actor: str,
    ) -> TemplateVersion:
        source = Path(source_path)
        if source.suffix.lower() != ".xls":
            raise TemplateServiceError(
                "TEMPLATE_FORMAT_UNSUPPORTED", "审核模板只接受 XLS 文件。"
            )
        if not source.is_file():
            raise TemplateServiceError("TEMPLATE_FILE_MISSING", "上传模板不存在。")
        name, version, actor = name.strip(), version.strip(), actor.strip()
        if not name or not version or not actor:
            raise TemplateServiceError(
                "TEMPLATE_METADATA_INVALID", "模板名称、版本和操作人不能为空。"
            )
        if self._bundle.templates.find_by_name_version(name, version) is not None:
            raise TemplateServiceError(
                "TEMPLATE_VERSION_EXISTS", f"模板 {name} {version} 已存在。"
            )
        validation = self._validator.validate(source, expected_version=version)
        template_id = uuid4()
        destination_dir = self._template_root / str(template_id)
        destination = destination_dir / "source.xls"
        stat = source.stat()
        digest = self._digest(source)
        destination_dir.mkdir(parents=True, exist_ok=False)
        try:
            shutil.copy2(source, destination)
            if self._digest(destination) != digest:
                raise TemplateServiceError(
                    "TEMPLATE_COPY_MISMATCH", "模板受管副本与上传内容不一致。"
                )
            now = datetime.now(timezone.utc)
            template = TemplateVersion(
                id=template_id,
                name=name,
                version=version,
                status=TemplateStatus.DRAFT,
                source_filename=original_name,
                source_path=destination,
                source_sha256=digest,
                source_size_bytes=stat.st_size,
                source_mtime_ns=stat.st_mtime_ns,
                source_rows=validation.matched_source_rows,
                effective_rules=len(A11Registry.executed_rules()),
                validation_findings=validation.findings,
                created_by=actor,
                created_at=now,
                updated_at=now,
                published_at=None,
            )
            return self._bundle.templates.create(
                template, self._baseline_rules(template_id, now)
            )
        except Exception:
            shutil.rmtree(destination_dir, ignore_errors=True)
            raise

    def list_versions(self) -> tuple[TemplateVersion, ...]:
        return self._bundle.templates.list_versions()

    def detail(self, template_id: UUID) -> dict[str, object]:
        try:
            return {
                "template": self._bundle.templates.get(template_id),
                "rules": self._bundle.templates.list_rules(template_id),
            }
        except RepositoryNotFoundError as error:
            raise TemplateServiceError("TEMPLATE_NOT_FOUND", "模板版本不存在。") from error

    def published_binding(
        self, template_id: UUID | None
    ) -> tuple[TemplateVersion, tuple[TemplateRule, ...]]:
        if template_id is None:
            template = self._bundle.templates.find_by_name_version(TEMPLATE_NAME, "A11")
            if template is None:
                raise TemplateServiceError("TEMPLATE_NOT_FOUND", "已发布的 A11 模板不存在。")
        else:
            try:
                template = self._bundle.templates.get(template_id)
            except RepositoryNotFoundError as error:
                raise TemplateServiceError("TEMPLATE_NOT_FOUND", "模板版本不存在。") from error
        if template.status is not TemplateStatus.PUBLISHED:
            raise TemplateServiceError("TEMPLATE_STATE_INVALID", "创建任务只能选择已发布模板。")
        rules = self._bundle.templates.list_rules(template.id)
        if not any(rule.enabled for rule in rules):
            raise TemplateServiceError("TEMPLATE_STATE_INVALID", "已发布模板没有启用的校验项。")
        return template, rules

    def update_rule(
        self, template_id: UUID, rule_id: str, changes: dict[str, object]
    ) -> TemplateRule:
        template = self._require_draft(template_id)
        rule = self._find_rule(template_id, rule_id)
        allowed = {
            "summary",
            "verifiable_requirement",
            "required_materials",
            "main_judgment",
            "confirmed_boundary",
            "enabled",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise TemplateServiceError(
                "TEMPLATE_RULE_UPDATE_INVALID",
                "包含不可修改的规则字段。",
                {"fields": sorted(unknown)},
            )
        normalized = dict(changes)
        if normalized.get("enabled") is False and "main_judgment" not in normalized:
            normalized["main_judgment"] = "DISABLED"
        if normalized.get("enabled") is True and rule.main_judgment == "DISABLED" and "main_judgment" not in normalized:
            normalized["main_judgment"] = "MANUAL"
        normalized["updated_at"] = datetime.now(timezone.utc)
        try:
            updated = rule.model_copy(update=normalized)
            self._bundle.templates.update_rule(updated)
        except (ValidationError, RepositoryConflictError) as error:
            raise TemplateServiceError(
                "TEMPLATE_RULE_UPDATE_INVALID", "规则修改不符合约束。"
            ) from error
        self._refresh_draft(template)
        return updated

    def add_rule(self, template_id: UUID, payload: dict[str, object]) -> TemplateRule:
        template = self._require_draft(template_id)
        rules = self._bundle.templates.list_rules(template_id)
        now = datetime.now(timezone.utc)
        try:
            rule = TemplateRule(
                id=uuid4(),
                template_id=template_id,
                source_row=None,
                source_sequence=max((item.source_sequence for item in rules), default=0) + 1,
                created_at=now,
                updated_at=now,
                **payload,
            )
            self._bundle.templates.add_rule(rule)
        except (TypeError, ValidationError, RepositoryConflictError) as error:
            raise TemplateServiceError(
                "TEMPLATE_RULE_INVALID", "新增规则不符合约束或编号已存在。"
            ) from error
        self._refresh_draft(template)
        return rule

    def delete_rule(self, template_id: UUID, rule_id: str) -> None:
        template = self._require_draft(template_id)
        try:
            self._bundle.templates.delete_rule(template_id, rule_id)
        except RepositoryNotFoundError as error:
            raise TemplateServiceError("TEMPLATE_RULE_NOT_FOUND", "规则不存在。") from error
        self._refresh_draft(template)

    def publish(self, template_id: UUID) -> TemplateVersion:
        template = self._require_draft(template_id)
        template = self._refresh_draft(template)
        blockers = tuple(
            item for item in template.validation_findings if item.severity == "ERROR"
        )
        if blockers:
            raise TemplateServiceError(
                "TEMPLATE_PUBLISH_BLOCKED",
                f"仍有 {len(blockers)} 项结构问题阻止发布。",
                {"findings": [item.model_dump(mode="json") for item in blockers]},
            )
        now = datetime.now(timezone.utc)
        published = template.model_copy(
            update={
                "status": TemplateStatus.PUBLISHED,
                "updated_at": now,
                "published_at": now,
            }
        )
        return self._bundle.templates.update_version(published)

    def retire(self, template_id: UUID) -> TemplateVersion:
        try:
            template = self._bundle.templates.get(template_id)
        except RepositoryNotFoundError as error:
            raise TemplateServiceError("TEMPLATE_NOT_FOUND", "模板版本不存在。") from error
        if template.status is not TemplateStatus.PUBLISHED:
            raise TemplateServiceError(
                "TEMPLATE_STATE_INVALID", "只有已发布模板可以停用。"
            )
        retired = template.model_copy(
            update={
                "status": TemplateStatus.RETIRED,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return self._bundle.templates.update_version(retired)

    def _require_draft(self, template_id: UUID) -> TemplateVersion:
        try:
            template = self._bundle.templates.get(template_id)
        except RepositoryNotFoundError as error:
            raise TemplateServiceError("TEMPLATE_NOT_FOUND", "模板版本不存在。") from error
        if template.status is not TemplateStatus.DRAFT:
            raise TemplateServiceError(
                "TEMPLATE_IMMUTABLE", "已发布或已停用模板不可修改。"
            )
        return template

    def _find_rule(self, template_id: UUID, rule_id: str) -> TemplateRule:
        for rule in self._bundle.templates.list_rules(template_id):
            if rule.rule_id == rule_id:
                return rule
        raise TemplateServiceError("TEMPLATE_RULE_NOT_FOUND", "规则不存在。")

    def _refresh_draft(self, template: TemplateVersion) -> TemplateVersion:
        current = self._bundle.templates.get(template.id)
        rules = self._bundle.templates.list_rules(template.id)
        findings = [
            item
            for item in current.validation_findings
            if not item.code.startswith("RULE_")
        ]
        if not any(rule.enabled for rule in rules):
            findings.append(
                TemplateValidationFinding(
                    code="RULE_NO_ACTIVE_ITEMS",
                    severity="ERROR",
                    message="模板至少需要一个启用的校验项。",
                )
            )
        for rule in rules:
            if rule.enabled and (rule.main_judgment == "MANUAL" or rule.source_row is None):
                findings.append(
                    TemplateValidationFinding(
                        code="RULE_MANUAL_REVIEW_REQUIRED",
                        severity="WARNING",
                        message=f"{rule.rule_id} 未配置可执行自动规则，审核时进入待人工确认。",
                        structural_address=(
                            f"{CHECKLIST_SHEET}!A{rule.source_row}"
                            if rule.source_row is not None
                            else None
                        ),
                    )
                )
        refreshed = current.model_copy(
            update={
                "effective_rules": sum(rule.enabled for rule in rules),
                "validation_findings": tuple(findings),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return self._bundle.templates.update_version(refreshed)

    @staticmethod
    def _baseline_rules(template_id: UUID, timestamp: datetime) -> tuple[TemplateRule, ...]:
        return tuple(
            TemplateRule(
                id=uuid5(NAMESPACE_URL, f"{template_id}:{definition.id}"),
                template_id=template_id,
                rule_id=definition.id,
                source_row=definition.source_row,
                source_sequence=definition.source_sequence,
                summary=definition.summary,
                verifiable_requirement=definition.verifiable_requirement,
                required_materials=definition.required_materials,
                main_judgment=definition.main_judgment,
                confirmed_boundary=definition.confirmed_boundary,
                enabled=definition.enabled,
                created_at=timestamp,
                updated_at=timestamp,
            )
            for definition in A11Registry.source_rows()
        )

    @staticmethod
    def _digest(path: Path) -> str:
        digest = sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
