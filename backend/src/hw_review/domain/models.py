"""Normalized, transport-safe domain models."""

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import quote
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .enums import (
    EvidenceKind,
    FileRole,
    FinalStatus,
    ReviewStatus,
    TaskState,
    TemplateStatus,
)
from .hashing import normalized_text_hash, ordered_identity_hash


class DomainModel(BaseModel):
    """Immutable model base that validates every supported copy operation."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    def model_copy(
        self: Self,
        *,
        update: Mapping[str, object] | None = None,
        deep: bool = False,
    ) -> Self:
        """Reconstruct through validation so updates cannot bypass invariants."""

        payload: dict[str, object] = dict(self.model_dump(round_trip=True))
        if update:
            payload.update(update)
        return type(self).model_validate(payload)


class SourceFileCreate(DomainModel):
    """Metadata supplied with a primary report or supporting evidence file."""

    role: FileRole
    original_name: str = Field(min_length=1)
    evidence_kinds: tuple[EvidenceKind, ...] = ()

    @model_validator(mode="after")
    def validate_evidence_kinds(self) -> "SourceFileCreate":
        if self.role is FileRole.SUPPORTING_EVIDENCE and not self.evidence_kinds:
            raise ValueError("evidence_kinds are required for supporting evidence")
        if self.role is FileRole.PRIMARY_REPORT and self.evidence_kinds:
            raise ValueError("evidence_kinds are not allowed for a primary report")
        return self


class StagedFile(DomainModel):
    """Verified task-local copy supplied to document parsers."""

    id: UUID
    task_id: UUID
    role: FileRole
    evidence_kinds: tuple[EvidenceKind, ...] = ()
    original_name: str = Field(min_length=1)
    detected_format: Literal["XLS", "XLSX", "DOC", "DOCX", "PDF"]
    path: Path
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_mtime_ns: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_evidence_kinds(self) -> "StagedFile":
        if self.role is FileRole.SUPPORTING_EVIDENCE and not self.evidence_kinds:
            raise ValueError("evidence_kinds are required for supporting evidence")
        if self.role is FileRole.PRIMARY_REPORT and self.evidence_kinds:
            raise ValueError("evidence_kinds are not allowed for a primary report")
        return self


JsonScalar = str | int | float | bool | None


def _a1_address(row: int, column: int) -> str:
    letters = ""
    value = column + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row + 1}"


class ParseWarning(DomainModel):
    """Stable, non-fatal parser limitation or source-file observation."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    structural_address: str | None = None


class ConversionProvenance(DomainModel):
    """Hashes and bounded runtime facts for a derived Word conversion."""

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    html_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    structured_json_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    word_version: str = Field(min_length=1)
    duration_seconds: float = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)


class TableCell(DomainModel):
    """One non-empty spreadsheet cell with a stable structural locator."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=False)

    row: int = Field(ge=0)
    column: int = Field(ge=0)
    address: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    structural_address: str = Field(min_length=1)
    raw_value: JsonScalar = None
    display_value: str
    formula_if_available: str | None = None
    cached_formula_value: JsonScalar = None
    merged_range: str | None = Field(
        default=None,
        pattern=r"^[A-Z]+[1-9][0-9]*:[A-Z]+[1-9][0-9]*$",
    )
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_addresses(self) -> "TableCell":
        if self.address != _a1_address(self.row, self.column):
            raise ValueError("row and column must agree with address")
        if not self.structural_address.endswith(f"/cell:{self.address}"):
            raise ValueError("structural_address must end with the cell address")
        if self.merged_range is not None and not self.merged_range.startswith(
            f"{self.address}:"
        ):
            raise ValueError("merged_range must start at the represented master cell")
        if self.content_hash != normalized_text_hash(self.display_value):
            raise ValueError(
                "content_hash must equal the normalized display text hash"
            )
        return self


class ContentBlock(DomainModel):
    """Ordered normalized content within a sheet or page."""

    id: UUID
    kind: Literal["text", "table", "image", "attachment"]
    order: int = Field(ge=0)
    structural_address: str = Field(min_length=1)
    text: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cells: tuple[TableCell, ...] = ()

    @model_validator(mode="after")
    def validate_cells(self) -> "ContentBlock":
        if self.kind == "table":
            if not self.cells:
                raise ValueError("table blocks require at least one cell")
            coordinates = [(cell.row, cell.column) for cell in self.cells]
            if coordinates != sorted(coordinates):
                raise ValueError("table cells must be ordered by row and column")
            if len(coordinates) != len(set(coordinates)):
                raise ValueError("table cells must have unique coordinates")
            expected_hash = ordered_identity_hash(
                f"{cell.structural_address}\0{cell.content_hash}"
                for cell in self.cells
            )
            if self.content_hash != expected_hash:
                raise ValueError(
                    "table content_hash must match ordered cell identities"
                )
        elif self.cells:
            raise ValueError("only table blocks may contain cells")
        if self.kind == "text":
            if self.text is None:
                raise ValueError("text blocks require text")
            if self.content_hash != normalized_text_hash(self.text):
                raise ValueError("text content_hash must match normalized text")
        return self


class DocumentContainer(DomainModel):
    """One source-preserved sheet or page and its ordered content."""

    id: UUID
    kind: Literal["sheet", "page"]
    name_or_number: Annotated[str, StringConstraints(strip_whitespace=False)] | int
    order: int = Field(ge=0)
    blocks: tuple[ContentBlock, ...] = ()

    @model_validator(mode="after")
    def validate_block_order(self) -> "DocumentContainer":
        if [block.order for block in self.blocks] != list(range(len(self.blocks))):
            raise ValueError("block order must be contiguous and zero-based")
        addresses = [block.structural_address for block in self.blocks]
        if len(addresses) != len(set(addresses)):
            raise ValueError("block structural addresses must be unique")
        if self.kind == "sheet":
            prefix = f"sheet:{self.order}:{quote(str(self.name_or_number), safe='')}"
            for block in self.blocks:
                if block.structural_address.startswith("workbook/object:"):
                    if block.kind not in {"image", "attachment"}:
                        raise ValueError(
                            "workbook object locators require image or attachment blocks"
                        )
                    continue
                if not block.structural_address.startswith(f"{prefix}/"):
                    raise ValueError(
                        "sheet block must match the container sheet locator prefix"
                    )
                for cell in block.cells:
                    if cell.structural_address != f"{prefix}/cell:{cell.address}":
                        raise ValueError(
                            "sheet cell must match the container sheet locator prefix"
                        )
        return self


class ReportDocument(DomainModel):
    """Immutable normalized representation of one staged report file."""

    id: UUID
    source_file_id: UUID
    format: Literal["XLS", "XLSX", "DOC", "DOCX", "PDF"]
    parser_version: str = Field(min_length=1)
    container_count: int = Field(ge=0)
    text_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    parse_warnings: tuple[ParseWarning, ...] = ()
    containers: tuple[DocumentContainer, ...] = ()
    conversion_provenance: ConversionProvenance | None = None

    @model_validator(mode="after")
    def validate_containers(self) -> "ReportDocument":
        if self.container_count != len(self.containers):
            raise ValueError("container_count must agree with containers")
        if [container.order for container in self.containers] != list(
            range(len(self.containers))
        ):
            raise ValueError("container order must be contiguous and zero-based")
        expected_digest = ordered_identity_hash(
            f"{container.order}\0{block.order}\0{block.structural_address}\0{block.content_hash}"
            for container in self.containers
            for block in container.blocks
        )
        if self.text_digest != expected_digest:
            raise ValueError("text_digest must match ordered block identities")
        return self

    def find_cell(self, sheet_name: str, address: str) -> TableCell:
        """Find exactly one cell or raise a stable lookup failure."""

        from hw_review.parsers.base import DocumentLookupError

        normalized_address = address.strip().upper()
        matches = [
            cell
            for container in self.containers
            if container.kind == "sheet" and container.name_or_number == sheet_name
            for block in container.blocks
            if block.kind == "table"
            for cell in block.cells
            if cell.address == normalized_address
        ]
        if not matches:
            raise DocumentLookupError(
                "CELL_NOT_FOUND", f"cell {sheet_name}!{normalized_address} was not found"
            )
        if len(matches) != 1:
            raise DocumentLookupError(
                "DUPLICATE_CELL",
                f"cell {sheet_name}!{normalized_address} is not unique",
            )
        return matches[0]


class EvidenceLocator(DomainModel):
    """Stable address of an evidentiary item inside a staged source file."""

    source_file_id: UUID
    container: str
    structural_address: str
    bbox: tuple[float, float, float, float] | None = None
    quoted_text: str | None = None
    content_hash: str


class AtomicResult(DomainModel):
    """One deterministic rule-check outcome and its traceable diagnostics."""

    status: ReviewStatus
    basis_code: str = Field(min_length=1)
    basis_text: str = Field(min_length=1)
    evidence: tuple[EvidenceLocator, ...] = ()
    missing_materials: tuple[str, ...] = ()
    unresolved_semantics: tuple[str, ...] = ()


class RuleDefinition(DomainModel):
    """One frozen visible row in the published A11 checklist baseline."""

    id: str = Field(pattern=r"^TR-[0-9]{2}$")
    source_row: int = Field(ge=1)
    source_sequence: int = Field(ge=1)
    summary: str = Field(min_length=1)
    verifiable_requirement: str = Field(min_length=1)
    required_materials: str = Field(min_length=1)
    main_judgment: Literal["RULE", "RULE_PLUS_AI", "AI", "DISABLED"]
    confirmed_boundary: str = Field(min_length=1)
    enabled: bool
    registry_version: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_enabled_judgment(self) -> "RuleDefinition":
        if self.enabled == (self.main_judgment == "DISABLED"):
            raise ValueError("enabled and main_judgment must agree")
        return self


def _template_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(timezone.utc)


class TemplateValidationFinding(DomainModel):
    """One persisted structural blocker or non-blocking publication warning."""

    code: str = Field(min_length=1)
    severity: Literal["ERROR", "WARNING"]
    message: str = Field(min_length=1)
    structural_address: str | None = None


class TemplateVersion(DomainModel):
    """One immutable-or-draft uploaded template version."""

    id: UUID
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: TemplateStatus
    source_filename: str = Field(min_length=1)
    source_path: Path
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(ge=0)
    source_mtime_ns: int = Field(ge=0)
    source_rows: int = Field(ge=0)
    effective_rules: int = Field(ge=0)
    validation_findings: tuple[TemplateValidationFinding, ...] = ()
    created_by: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None

    _normalize_created_at = field_validator("created_at")(_template_utc_datetime)
    _normalize_updated_at = field_validator("updated_at")(_template_utc_datetime)
    _normalize_published_at = field_validator("published_at")(_template_utc_datetime)

    @model_validator(mode="after")
    def validate_publication_time(self) -> "TemplateVersion":
        if self.status is TemplateStatus.PUBLISHED and self.published_at is None:
            raise ValueError("published templates require published_at")
        if self.status is TemplateStatus.DRAFT and self.published_at is not None:
            raise ValueError("draft templates cannot have published_at")
        return self


class TemplateRule(DomainModel):
    """One editable draft rule or immutable published rule snapshot."""

    id: UUID
    template_id: UUID
    rule_id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,31}$")
    source_row: int | None = Field(default=None, ge=1)
    source_sequence: int = Field(ge=1)
    summary: str = Field(min_length=1)
    verifiable_requirement: str = Field(min_length=1)
    required_materials: str = Field(min_length=1)
    main_judgment: Literal["RULE", "RULE_PLUS_AI", "AI", "MANUAL", "DISABLED"]
    confirmed_boundary: str = Field(min_length=1)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    _normalize_created_at = field_validator("created_at")(_template_utc_datetime)
    _normalize_updated_at = field_validator("updated_at")(_template_utc_datetime)

    @model_validator(mode="after")
    def validate_enabled_judgment(self) -> "TemplateRule":
        if self.enabled == (self.main_judgment == "DISABLED"):
            raise ValueError("enabled and main_judgment must agree")
        return self


class ReviewSource(DomainModel):
    """A source file paired with its normalized immutable document."""

    source_file: StagedFile
    document: ReportDocument

    @model_validator(mode="after")
    def validate_document_identity(self) -> "ReviewSource":
        if self.document.source_file_id != self.source_file.id:
            raise ValueError("document source_file_id must equal source file id")
        return self


def _review_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(timezone.utc)


from .ports import DocumentQuery


class ReviewInput(DomainModel):
    """Ordered, revision-bound input to deterministic rule evaluation."""

    model_config = ConfigDict(
        frozen=True, str_strip_whitespace=True, arbitrary_types_allowed=True
    )

    task_id: UUID
    active_revision_no: int = Field(ge=0)
    sources: tuple[ReviewSource, ...] = Field(min_length=1)
    evaluated_at: datetime
    query: DocumentQuery

    _normalize_evaluated_at = field_validator("evaluated_at")(_review_utc_datetime)

    @model_validator(mode="after")
    def validate_sources_and_query(self) -> "ReviewInput":
        if not any(
            item.source_file.role is FileRole.PRIMARY_REPORT for item in self.sources
        ):
            raise ValueError("at least one primary report source is required")
        if any(item.source_file.task_id != self.task_id for item in self.sources):
            raise ValueError("every source task_id must equal review task_id")
        required_methods = ("find_text", "find_nonempty_labels", "has_evidence_kind")
        if not all(callable(getattr(self.query, name, None)) for name in required_methods):
            raise ValueError("query must implement DocumentQuery")
        return self


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(timezone.utc)


class ReviewTask(DomainModel):
    """Persisted lifecycle and display facts for one review task."""

    id: UUID
    state: TaskState
    active_revision_no: int = Field(ge=0)
    display_name: str = Field(min_length=1)
    template_version: str = Field(min_length=1)
    template_id: UUID | None = None
    template_name: str = "硬件测试过程检查单"
    template_source_path: Path | None = None
    template_source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    template_rules_snapshot: str = "[]"
    created_at: datetime
    updated_at: datetime

    _normalize_created_at = field_validator("created_at")(_utc_datetime)
    _normalize_updated_at = field_validator("updated_at")(_utc_datetime)


class RuleResult(DomainModel):
    """Frozen system result for one rule in one active task revision."""

    id: UUID
    task_id: UUID
    rule_id: str = Field(min_length=1)
    initial_status: ReviewStatus
    basis_code: str = Field(min_length=1)
    basis_text: str = Field(min_length=1)
    evidence_locators: tuple[EvidenceLocator, ...] = ()
    missing_materials: tuple[str, ...] = ()
    unresolved_semantics: tuple[str, ...] = ()
    engine_version: str = Field(min_length=1)
    baseline_version: str = Field(default="A11", min_length=1)
    active_revision_no: int = Field(ge=0)
    created_at: datetime

    _normalize_created_at = field_validator("created_at")(_utc_datetime)


class ManualDecision(DomainModel):
    """Human final decision linked to the system result it supersedes."""

    id: UUID
    rule_result_id: UUID
    final_status: FinalStatus
    reason: str = Field(min_length=1)
    supplemental_evidence: tuple[EvidenceLocator, ...] = ()
    actor: str = Field(min_length=1)
    decided_at: datetime

    _normalize_decided_at = field_validator("decided_at")(_utc_datetime)


class ReviewRevision(DomainModel):
    """Immutable completed-review snapshot."""

    id: UUID
    task_id: UUID
    revision_no: int = Field(ge=1)
    completed_at: datetime
    result_snapshot: str = Field(min_length=1)

    _normalize_completed_at = field_validator("completed_at")(_utc_datetime)


class StageFailure(DomainModel):
    """A stable, persisted execution failure with no implementation traceback."""

    id: UUID
    task_id: UUID
    stage: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    occurred_at: datetime

    _normalize_occurred_at = field_validator("occurred_at")(_utc_datetime)
