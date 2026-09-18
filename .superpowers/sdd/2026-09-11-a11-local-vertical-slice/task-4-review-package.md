# Task 4 Independent Review Package

Review Task 4 as a direct complete-file review because Git is intentionally unavailable. Do not edit files and do not spawn subagents.

## Requirements

- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-4-brief.md`
- `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md` Task 4
- `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md` sections 4, 5.1, 5.2, 9, and 10
- `docs/requirements/a11-validation-sample-catalog-v0.1.md` S-01

## Implementation and evidence

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/src/hw_review/parsers/__init__.py`
- `backend/src/hw_review/parsers/base.py`
- `backend/src/hw_review/parsers/xls.py`
- `backend/src/hw_review/services/parsing.py`
- `backend/tests/unit/test_parser_contract.py`
- `backend/tests/integration/test_xls_parser.py`
- `backend/pyproject.toml`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-4-report.md`

Claimed final evidence: focused 15/15, full backend 105/105, compileall clean. S-01 parsed only from staged copy in about 0.45 seconds: 18 sheets, 6,358 nonempty cells, 56 opaque embedded objects/streams; source fingerprint unchanged; task directory removed.

## Review priorities

1. Normalized models are immutable and self-consistent, preserve empty source containers, stable order/address/hash identity, and provide reliable unique cell lookup.
2. XLS parsing verifies the staged file identity, reads only the copy, preserves sheet order, values/merges/addresses, does not recalculate formulas, and emits honest warnings.
3. OLE inventory cannot execute content and uses deterministic opaque identities without claiming semantic interpretation.
4. Parser errors and registry errors are stable and format dispatch is extension-independent.
5. S-01 evidence is genuinely read-only, cleanup is reliable even on failure, and no business-correctness claim is derived.
6. Tests exercise malformed data and cross-field invariants rather than mirroring implementation.
7. The normalized contract remains usable by DOC/PDF adapters and A11 evidence generation in later tasks.

You may rerun tests with bundled Python and a fresh repository-local `--basetemp`. Do not modify or reparse any real sample unless necessary; if you do, use the established read-only staging/fingerprint/cleanup path.

## Required response

Return findings ordered Critical, Important, Minor with exact file/line references. Then return:

- `Spec compliance: PASS|FAIL`
- `Task quality: PASS|FAIL`

If a verdict fails, give the minimum concrete fixes/tests. Ignore formatting-only preferences.
