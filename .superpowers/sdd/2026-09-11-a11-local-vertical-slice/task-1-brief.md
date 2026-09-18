# Task 1 brief — Python 工程骨架与领域契约

Read this first. It is the complete Task 1 requirement set extracted from `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md`.

## Binding global constraints

- Do not use Git or initialize a repository.
- Use Python 3.12 and the resolved bundled executable unless a workspace-local virtual environment is created.
- Development persistence is SQLite; production database remains undecided.
- No LLM, OCR, formal XLS writing, real authentication, or template-management backend.
- System statuses are exactly `COMPLIANT`, `NON_COMPLIANT`, `NOT_APPLICABLE`, `NEEDS_REVIEW`; manual final statuses exclude `NEEDS_REVIEW`.
- Evidence kinds are exactly `JIRA_RECORD`, `PREVIOUS_STAGE_REPORT`, `POWER_RECORD`, `REQUIREMENT_OR_CASE_MAPPING`, `PAPER_RECORD`, `EMC_REPORT`, `TEMPERATURE_RECORD`, `AUTOMATION_RECORD`, `PUBLISHED_CRITERIA`, `OTHER`.
- Apply strict TDD: create tests, observe the expected RED, then implement, then run GREEN.

## Files

- Create `backend/pyproject.toml`.
- Create package initializers at `backend/src/hw_review/__init__.py` and `backend/src/hw_review/domain/__init__.py`.
- Create `backend/src/hw_review/config.py`.
- Create `backend/src/hw_review/domain/enums.py`.
- Create `backend/src/hw_review/domain/models.py`.
- Create `backend/src/hw_review/domain/ports.py`.
- Create `backend/tests/unit/test_domain_contracts.py`.
- Write the full implementation report to `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-report.md`.

## Required interfaces and behavior

- Export `ReviewStatus`, `FinalStatus`, `TaskState`, `FileRole`, and `EvidenceKind`.
- Export normalized Pydantic models and parser/repository/clock protocols used by later tasks.
- `SourceFileCreate` fields: `role: FileRole`, `original_name: str`, `evidence_kinds: tuple[EvidenceKind, ...] = ()`.
- `EvidenceLocator` fields: `source_file_id: UUID`, `container: str`, `structural_address: str`, optional four-number `bbox`, optional `quoted_text`, and `content_hash: str`.
- `AtomicResult` fields: `status`, `basis_code`, `basis_text`, `evidence`, `missing_materials`, `unresolved_semantics`.
- A supporting file with no evidence kind must fail validation; a primary report must not carry evidence kinds.
- Do not add status aliases or extra evidence kinds.

## Required RED/GREEN tests

```python
def test_review_and_final_status_sets_are_exact():
    assert {s.value for s in ReviewStatus} == {
        "COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE", "NEEDS_REVIEW"
    }
    assert {s.value for s in FinalStatus} == {
        "COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE"
    }

def test_supporting_file_requires_evidence_kind():
    with pytest.raises(ValueError, match="evidence_kinds"):
        SourceFileCreate(
            role=FileRole.SUPPORTING_EVIDENCE,
            original_name="jira.pdf",
            evidence_kinds=[],
        )
```

Add tests for primary evidence-kind rejection, exact task-state values, evidence-locator bbox cardinality, nonblank basis fields, and runtime-checkable protocol signatures.

Run the focused test before implementation and record the expected missing-module RED. After implementation run the focused file and the complete backend suite. The report must contain commands, exit codes, pass counts, exact files changed, dependency-install status, and self-review concerns. Do not spawn subagents.
