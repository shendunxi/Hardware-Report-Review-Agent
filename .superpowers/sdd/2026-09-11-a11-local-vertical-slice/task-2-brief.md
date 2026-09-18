# Task 2 Brief — read-only staging, signature detection, and bounded cleanup

## Objective

Implement the task-local file staging boundary and its cleanup guardrails. This task must prove that a source file is copied without mutation, detected by content signature rather than extension alone, and that recursive deletion can only target a verified UUID-named direct child of the configured work root.

## Source of truth

- Plan: `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md`, Task 2.
- Design: `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md`, sections 4.1, 5.1, and 9.
- Existing contracts: `backend/src/hw_review/domain/enums.py`, `models.py`, and `ports.py`.
- Ledger rulings: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/progress.md`.

## Allowed files

- Create `backend/src/hw_review/services/__init__.py`.
- Create `backend/src/hw_review/services/staging.py`.
- Create `backend/src/hw_review/services/cleanup.py`.
- Create `backend/tests/unit/test_staging.py`.
- Create `backend/tests/unit/test_cleanup.py`.
- Create or update only the minimum domain export/model file needed to introduce `StagedFile`.
- Create `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-2-report.md`.

Do not modify requirements, design, plan, prototype, persistence, parser, rule, orchestration, or API files. Do not use Git. Do not access or mutate the user's real sample files in this task.

## Required public behavior

- `fingerprint(path)` returns stable source facts sufficient to compare SHA-256, size, and modification time.
- `FileStager.stage(source: Path, task_id: UUID, metadata: SourceFileCreate) -> StagedFile`:
  - resolves and reads the source, creates `<work_root>/<task UUID>/input/`, and stores the copy under a generated UUID-based name; the user filename is metadata only;
  - recognizes `%PDF-`, OLE Compound File (`D0 CF 11 E0 A1 B1 1A E1`), and OOXML ZIP signatures;
  - disambiguates OLE XLS vs DOC using compound-directory stream names (`Workbook`/`Book` versus `WordDocument`), not the filename extension;
  - disambiguates OOXML XLSX vs DOCX using package entries;
  - accepts the project-supported primary formats XLS, XLSX, DOC, DOCX, and PDF, while preserving a normalized uppercase `detected_format`;
  - rejects unsupported, corrupt, ambiguous, or extension/signature-conflicting inputs with a stable `StageError.code`; extension/signature conflict must be `FILE_SIGNATURE_MISMATCH`;
  - uses `shutil.copy2`, compares source/copy hashes, and removes an incomplete staged copy on failure;
  - does not mutate source contents or metadata.
- `StagedFile` is an immutable validated domain model carrying at least generated file ID, task ID, role, evidence kinds, original display name, detected format, staged `Path`, byte size, SHA-256, and source modification time. It must remain suitable as Task 4 parser input.
- `WorkspaceCleaner.clean_task(task_id)` and `WorkspaceCleaner.clean_expired(now)`:
  - resolve configured root and target;
  - only recursively delete a non-symlink UUID-named directory whose resolved parent is exactly the configured root;
  - refuse the root itself, siblings, ancestors, nested arbitrary paths, non-UUID names, and symlinks with `CleanupSafetyError`;
  - `clean_expired(now)` removes only eligible task directories whose age is at least the configured expiry (default 24 hours), returns removed task UUIDs in deterministic order, and leaves active/non-task entries untouched.

## Required tests and TDD evidence

Write tests first and record an actual RED run before implementation. Include at least:

1. Source fingerprint before and after staging is identical; staged hash equals source hash; destination parent is `input`; stored filename is generated rather than derived from the display name.
2. Correct signature detection for PDF and OOXML packages plus OLE XLS/DOC stream disambiguation. Fixtures may be synthetic or safely mocked at the compound-directory inspection boundary, but production detection must inspect package/compound entries.
3. Extension/signature mismatch returns `FILE_SIGNATURE_MISMATCH`.
4. Ambiguous/unsupported/corrupt data returns stable, tested errors.
5. Copy verification failure leaves no staged payload.
6. Cleanup refuses every out-of-root/unsafe target category above.
7. Expired cleanup deletes only expired UUID task directories, leaves active directories and unrelated entries, and has deterministic output.

Run with the recorded bundled Python:

`C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests/unit/test_staging.py tests/unit/test_cleanup.py -v`

Then run the full backend test suite. Do not weaken Task 1 contracts or tests.

## Report

In `task-2-report.md`, record:

- RED command and exact failure summary;
- GREEN focused and full-suite commands and pass counts;
- exact files created/modified;
- one source-before/source-after fingerprint example;
- cleanup refusal assertions and expiry result;
- deviations or unresolved risks;
- explicitly state that no Git commit exists by user constraint.

## Completion gate

Stop only after the focused suite and full backend suite pass, the report is written, and all cleanup operations used in tests are confined to temporary test directories.
