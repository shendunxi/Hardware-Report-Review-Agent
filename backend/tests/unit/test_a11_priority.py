from uuid import uuid4

import pytest

from hw_review.domain.enums import ReviewStatus
from hw_review.domain.models import AtomicResult, EvidenceLocator
from hw_review.rules.a11_engine import rollup


def _atom(status: ReviewStatus, suffix: str = "A", **updates) -> AtomicResult:
    payload = {
        "status": status,
        "basis_code": f"BASIS_{suffix}",
        "basis_text": f"Basis {suffix}",
    }
    payload.update(updates)
    return AtomicResult(**payload)


@pytest.mark.parametrize(
    ("statuses", "expected", "basis_code"),
    [
        ((ReviewStatus.NOT_APPLICABLE, ReviewStatus.NOT_APPLICABLE), ReviewStatus.NOT_APPLICABLE, "ROLLUP_ALL_NOT_APPLICABLE"),
        ((ReviewStatus.NOT_APPLICABLE, ReviewStatus.COMPLIANT), ReviewStatus.COMPLIANT, "ROLLUP_ALL_APPLICABLE_COMPLIANT"),
        ((ReviewStatus.NOT_APPLICABLE, ReviewStatus.NEEDS_REVIEW), ReviewStatus.NEEDS_REVIEW, "ROLLUP_UNRESOLVED_SEMANTICS"),
        ((ReviewStatus.NEEDS_REVIEW, ReviewStatus.NON_COMPLIANT), ReviewStatus.NON_COMPLIANT, "ROLLUP_HARD_FAILURE"),
        ((ReviewStatus.COMPLIANT, ReviewStatus.NON_COMPLIANT), ReviewStatus.NON_COMPLIANT, "ROLLUP_HARD_FAILURE"),
        ((ReviewStatus.COMPLIANT, ReviewStatus.NEEDS_REVIEW), ReviewStatus.NEEDS_REVIEW, "ROLLUP_UNRESOLVED_SEMANTICS"),
        ((ReviewStatus.COMPLIANT, ReviewStatus.COMPLIANT), ReviewStatus.COMPLIANT, "ROLLUP_ALL_APPLICABLE_COMPLIANT"),
    ],
)
def test_rollup_priority(statuses, expected, basis_code) -> None:
    result = rollup(tuple(_atom(status, str(index)) for index, status in enumerate(statuses)))

    assert result.status is expected
    assert result.basis_code == basis_code
    assert result.basis_text


def test_rollup_merges_and_deduplicates_all_diagnostics_in_atom_order() -> None:
    locator = EvidenceLocator(
        source_file_id=uuid4(),
        container="Sheet1",
        structural_address="sheet:0:Sheet1/cell:B2",
        quoted_text="FAIL",
        content_hash="a" * 64,
    )
    atoms = (
        _atom(
            ReviewStatus.NEEDS_REVIEW,
            "P",
            evidence=(locator,),
            unresolved_semantics=("需比较", "需比较"),
        ),
        _atom(
            ReviewStatus.NON_COMPLIANT,
            "F",
            evidence=(locator,),
            missing_materials=("JIRA记录", "JIRA记录"),
            unresolved_semantics=("需确认通知",),
        ),
    )

    result = rollup(atoms)

    assert result.status is ReviewStatus.NON_COMPLIANT
    assert result.evidence == (locator,)
    assert result.missing_materials == ("JIRA记录",)
    assert result.unresolved_semantics == ("需比较", "需确认通知")


def test_rollup_rejects_empty_atoms() -> None:
    with pytest.raises(ValueError, match="at least one atom"):
        rollup(())
