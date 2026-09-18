import inspect
from typing import Any, get_args, get_origin, get_type_hints
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from hw_review.domain.enums import (
    EvidenceKind,
    FileRole,
    FinalStatus,
    ReviewStatus,
    TaskState,
)
from hw_review.domain.models import AtomicResult, EvidenceLocator, SourceFileCreate
from hw_review.domain.ports import (
    Clock,
    DocumentParser,
    ResultRepository,
    RevisionRepository,
    TaskRepository,
)


class _StagedFile(BaseModel):
    path: str


class _ReportDocument(BaseModel):
    identifier: str


class _Task(BaseModel):
    identifier: str


class _Result(BaseModel):
    identifier: str


class _Decision(BaseModel):
    identifier: str


class _Revision(BaseModel):
    identifier: str


class _Snapshot(BaseModel):
    identifier: str


def test_review_and_final_status_sets_are_exact():
    assert {status.value for status in ReviewStatus} == {
        "COMPLIANT",
        "NON_COMPLIANT",
        "NOT_APPLICABLE",
        "NEEDS_REVIEW",
    }
    assert {status.value for status in FinalStatus} == {
        "COMPLIANT",
        "NON_COMPLIANT",
        "NOT_APPLICABLE",
    }


def test_domain_enum_member_names_are_closed_without_aliases():
    assert tuple(ReviewStatus.__members__) == (
        "COMPLIANT",
        "NON_COMPLIANT",
        "NOT_APPLICABLE",
        "NEEDS_REVIEW",
    )
    assert tuple(FinalStatus.__members__) == (
        "COMPLIANT",
        "NON_COMPLIANT",
        "NOT_APPLICABLE",
    )
    assert tuple(TaskState.__members__) == (
        "CREATED",
        "FILES_STAGED",
        "PARSING",
        "PARSED",
        "EVALUATING",
        "READY_FOR_REVIEW",
        "COMPLETED",
        "FAILED",
    )
    assert tuple(FileRole.__members__) == ("PRIMARY_REPORT", "SUPPORTING_EVIDENCE")
    assert tuple(EvidenceKind.__members__) == (
        "JIRA_RECORD",
        "PREVIOUS_STAGE_REPORT",
        "POWER_RECORD",
        "REQUIREMENT_OR_CASE_MAPPING",
        "PAPER_RECORD",
        "EMC_REPORT",
        "TEMPERATURE_RECORD",
        "AUTOMATION_RECORD",
        "PUBLISHED_CRITERIA",
        "OTHER",
    )


def test_evidence_kind_set_is_exact():
    assert {kind.value for kind in EvidenceKind} == {
        "JIRA_RECORD",
        "PREVIOUS_STAGE_REPORT",
        "POWER_RECORD",
        "REQUIREMENT_OR_CASE_MAPPING",
        "PAPER_RECORD",
        "EMC_REPORT",
        "TEMPERATURE_RECORD",
        "AUTOMATION_RECORD",
        "PUBLISHED_CRITERIA",
        "OTHER",
    }


def test_supporting_file_requires_evidence_kind():
    with pytest.raises(ValueError, match="evidence_kinds"):
        SourceFileCreate(
            role=FileRole.SUPPORTING_EVIDENCE,
            original_name="jira.pdf",
            evidence_kinds=[],
        )


def test_primary_report_rejects_evidence_kinds():
    with pytest.raises(ValueError, match="evidence_kinds"):
        SourceFileCreate(
            role=FileRole.PRIMARY_REPORT,
            original_name="primary.xls",
            evidence_kinds=[EvidenceKind.JIRA_RECORD],
        )


def test_task_state_values_are_exact():
    assert {state.value for state in TaskState} == {
        "CREATED",
        "FILES_STAGED",
        "PARSING",
        "PARSED",
        "EVALUATING",
        "READY_FOR_REVIEW",
        "COMPLETED",
        "FAILED",
    }


def test_evidence_locator_accepts_exactly_four_bbox_numbers():
    locator = EvidenceLocator(
        source_file_id=uuid4(),
        container="Sheet1",
        structural_address="A1",
        bbox=(1.0, 2.0, 3.0, 4.0),
        content_hash="abc123",
    )

    assert locator.bbox == (1.0, 2.0, 3.0, 4.0)


@pytest.mark.parametrize("bbox", [(1.0, 2.0, 3.0), (1.0, 2.0, 3.0, 4.0, 5.0)])
def test_evidence_locator_rejects_bbox_that_is_not_four_numbers(bbox):
    with pytest.raises(ValidationError, match="bbox"):
        EvidenceLocator(
            source_file_id=uuid4(),
            container="Sheet1",
            structural_address="A1",
            bbox=bbox,
            content_hash="abc123",
        )


@pytest.mark.parametrize("field_name", ["basis_code", "basis_text"])
def test_atomic_result_rejects_blank_basis_fields(field_name):
    payload = {
        "status": ReviewStatus.COMPLIANT,
        "basis_code": "RULE_PASS",
        "basis_text": "All required evidence is present.",
    }
    payload[field_name] = "  "

    with pytest.raises(ValidationError, match=field_name):
        AtomicResult(**payload)


def test_domain_models_reject_public_assignment():
    models_and_assignments = [
        (
            SourceFileCreate(
                role=FileRole.PRIMARY_REPORT,
                original_name="primary.xls",
            ),
            "original_name",
            "renamed.xls",
        ),
        (
            EvidenceLocator(
                source_file_id=uuid4(),
                container="Sheet1",
                structural_address="A1",
                content_hash="abc123",
            ),
            "content_hash",
            "different",
        ),
        (
            AtomicResult(
                status=ReviewStatus.COMPLIANT,
                basis_code="RULE_PASS",
                basis_text="All required evidence is present.",
            ),
            "basis_text",
            "different",
        ),
    ]

    for model, attribute, value in models_and_assignments:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(model, attribute, value)


def test_primary_report_model_copy_revalidates_evidence_kinds():
    primary = SourceFileCreate(
        role=FileRole.PRIMARY_REPORT,
        original_name="primary.xls",
    )

    with pytest.raises(ValidationError, match="evidence_kinds"):
        primary.model_copy(update={"evidence_kinds": (EvidenceKind.JIRA_RECORD,)})


def test_atomic_result_model_copy_revalidates_blank_basis_text():
    result = AtomicResult(
        status=ReviewStatus.COMPLIANT,
        basis_code="RULE_PASS",
        basis_text="All required evidence is present.",
    )

    with pytest.raises(ValidationError, match="basis_text"):
        result.model_copy(update={"basis_text": "   "})


@pytest.mark.parametrize(
    ("protocol", "type_arguments", "method_parameters"),
    (
        (DocumentParser, (_StagedFile, _ReportDocument), {"parse": ("self", "staged")} ),
        (TaskRepository, (_Task,), {"create": ("self", "task"), "get": ("self", "task_id"), "update": ("self", "task")} ),
        (ResultRepository, (_Result,), {"replace_all": ("self", "task_id", "results"), "list_for_task": ("self", "task_id")} ),
        (RevisionRepository, (_Decision, _Revision, _Snapshot), {"complete": ("self", "task_id", "decisions"), "update_snapshot": ("self", "revision_id", "snapshot")} ),
    ),
)
def test_generic_ports_have_bounded_specializations_and_no_escape_annotations(
    protocol, type_arguments, method_parameters
):
    assert getattr(protocol, "_is_runtime_protocol", False)
    assert get_origin(protocol[type_arguments]) is protocol
    assert get_args(protocol[type_arguments]) == type_arguments
    assert all(type_parameter.__bound__ is BaseModel for type_parameter in protocol.__parameters__)
    assert {
        name
        for name, member in protocol.__dict__.items()
        if inspect.isfunction(member) and not name.startswith("_")
    } == set(method_parameters)

    for method_name, parameter_names in method_parameters.items():
        method = getattr(protocol, method_name)
        assert tuple(inspect.signature(method).parameters) == parameter_names
        annotations = get_type_hints(method)
        assert set(annotations) == {*parameter_names[1:], "return"}
        assert all(annotation not in (object, Any) for annotation in annotations.values())


def test_clock_port_is_runtime_checkable_and_has_fully_annotated_method():
    assert getattr(Clock, "_is_runtime_protocol", False)
    assert tuple(inspect.signature(Clock.now).parameters) == ("self",)
    assert get_type_hints(Clock.now)["return"].__name__ == "datetime"
