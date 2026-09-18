# Task 1 report - Python project skeleton and domain contracts

## Scope delivered

Implemented the Task 1 Python project entry point, closed domain vocabularies,
normalized Pydantic contract models, and runtime-checkable parser, repository,
and clock ports. No parser, persistence, rules, API, authentication, OCR, LLM,
or XLS-writing behavior was added.

## Runtime and dependency actions

- Bundled executable used for every command: `C:\\Users\\sdt52153\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe`
- `--version` output: `Python 3.12.14` (exit 0).
- Created `backend/pyproject.toml` before dependency installation. It declares only the Task 1 runtime requirements and the `pytest` test extra.
- First non-escalated attempt, `python -m pip install '.[test]'`, exited 1 because the restricted network could not download build dependency `setuptools` (`WinError 10013`).
- After approved escalation, ran `python -m pip install --user fastapi uvicorn 'pydantic>=2' 'sqlalchemy>=2' alembic python-multipart xlrd olefile pymupdf pywin32 psutil pytest` (exit 0). `pydantic 2.13.5` was already present; the remaining declared dependencies and pytest were installed.
- Import check output: `dependency imports: OK`; `pydantic=2.13.5; pytest=9.1.1` (exit 0). The check emitted PyMuPDF's upstream deprecation warning for the legacy `fitz` import; no Task 1 code imports `fitz`.

## Strict TDD evidence

### RED 1 - missing domain package

Command, from `backend`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\unit\test_domain_contracts.py -v
```

Exit 2. Pytest collected zero tests because the intended new test module could not import the absent production package:

```text
ModuleNotFoundError: No module named 'hw_review'
============================== 1 error in 0.21s ===============================
```

### RED 2 - closed evidence-kind vocabulary

Before restoring `EvidenceKind`, added its exact-set contract test and ran the same focused command. Exit 2, with the expected absent-contract error:

```text
ImportError: cannot import name 'EvidenceKind' from 'hw_review.domain.enums'
============================== 1 error in 0.15s ===============================
```

### GREEN - focused contract suite

Command, from `backend`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\unit\test_domain_contracts.py -v
```

Exit 0. Output: `13 passed in 0.11s`.

The tests cover exact review/final/evidence-kind/task-state vocabularies, supporting-file evidence requirement, primary-report evidence rejection, four-number bbox validation, nonblank atomic-result basis fields, and runtime-checkable protocol method signatures.

### GREEN - complete backend suite

Command, from `backend`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v
```

Exit 0. Output: `13 passed in 0.10s`. This is the complete suite currently configured by `testpaths = ["tests"]`.

## Authored files changed

- `backend/pyproject.toml`
- `backend/src/hw_review/__init__.py`
- `backend/src/hw_review/config.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/src/hw_review/domain/enums.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/ports.py`
- `backend/tests/unit/test_domain_contracts.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-report.md`

Pytest also generated its normal `backend/.pytest_cache/` and Python bytecode caches; they are not authored project contracts.

## Self-review

- Exact status and evidence-kind enums contain no aliases or additional values.
- `SourceFileCreate` normalizes whitespace and rejects both invalid role/evidence-kind combinations; the service remains responsible for the separate one-primary-per-task invariant, as required.
- `EvidenceLocator` uses an optional fixed four-float tuple; `AtomicResult` strips whitespace before enforcing nonblank basis fields.
- Ports are deliberately runtime-checkable and use only boundary signatures; their concrete adapters and richer entity types are deferred to the tasks that create them.
- Concern: `fitz` emitted an upstream deprecation warning in the dependency import probe. Task 1 does not use that API; a later PDF-adapter task should import the supported `pymupdf` module directly.

## Review round 1 - contract hardening

### RED - focused regression suite

Command, from `backend`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests\unit\test_domain_contracts.py -v
```

Exit 1. Output: `7 failed, 12 passed in 0.75s`.

The failures demonstrated each reviewed gap: all three public model assignments
were accepted; `SourceFileCreate.model_copy(update={"evidence_kinds": ...})`
and `AtomicResult.model_copy(update={"basis_text": "   "})` bypassed
validation; and all four parser/repository protocols raised `TypeError` when
specialized because they were not generic classes.

### GREEN - focused regression suite

Ran the same focused command after the implementation. Exit 0. Output:
`19 passed in 0.12s`.

The added regressions verify every enum's `__members__` names (including
`FileRole`), accepted four-number bbox values plus both shorter and longer
rejection cases, frozen direct assignment across all three domain models,
revalidated full-payload copy updates, and every generic protocol method's
signature and annotations. The ports specialize over bounded `BaseModel`
types without `object` or `Any` annotations.

### GREEN - complete backend suite

Command, from `backend`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v
```

Exit 0. Output: `19 passed in 0.22s`.

### Files changed in review round 1

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/ports.py`
- `backend/tests/unit/test_domain_contracts.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-report.md`

### Review-round self-check

- `DomainModel.model_copy` rebuilds from `model_dump(round_trip=True)` and
  calls the concrete model's `model_validate`, so normal public update paths
  run both field and model validators. Deliberate low-level
  `model_construct` bypasses remain outside the requested scope.
- Generic parser and repository type variables are bounded by `BaseModel`,
  which permits later Pydantic domain entities to specialize the contracts
  without creating premature parser or persistence entities.
