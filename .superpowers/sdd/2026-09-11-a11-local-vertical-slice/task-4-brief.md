# Task 4 Brief — normalized document contract and XLS adapter

## Objective

Define one immutable normalized document model and implement the first real parser adapter for legacy `.xls`. The parser must read only a Task 2 staged copy, preserve stable sheet/cell/merge addresses and evidence hashes, inventory embedded objects without executing them, and prove read-only compatibility against frozen sample S-01.

## Source of truth

- Plan: `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md`, Task 4.
- Design: `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md`, sections 4, 5.1, 5.2, and 10.
- Sample catalog: `docs/requirements/a11-validation-sample-catalog-v0.1.md`, S-01 only in this task.
- Existing `StagedFile`, `DocumentParser`, staging/cleanup, and persistence contracts.

## Binding boundaries

- Do not use Git.
- Real sample access is read-only. Never open it through Excel/Office, never write beside it, and never modify its contents or timestamps. Copy it through `FileStager` into a task-local workspace and parse only the staged copy.
- This task supports XLS only in production parser code. Do not implement XLSX, DOC, DOCX, PDF, OCR, formula recalculation, image OCR, embedded-object execution, rules, API, or UI.
- Do not infer business correctness from historical report content.
- A parse failure must be stable and explicit; never synthesize partial compliance results.
- Strict TDD is required.

## Files

Create:

- `backend/src/hw_review/parsers/__init__.py`
- `backend/src/hw_review/parsers/base.py`
- `backend/src/hw_review/parsers/xls.py`
- `backend/src/hw_review/services/parsing.py`
- `backend/tests/unit/test_parser_contract.py`
- `backend/tests/integration/test_xls_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-4-report.md`

Modify only as necessary:

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/src/hw_review/domain/ports.py` only if specializing the existing generic protocol requires a compatible export; do not weaken it.
- `backend/pyproject.toml` only for a declared test dependency if a synthetic XLS writer is required.

Do not modify persistence/staging implementation, requirements/design/plan, prototype, or prior tests.

## Required normalized models

Add the smallest immutable Pydantic models consistent with the design:

- `ReportDocument`: durable ID, `source_file_id`, normalized format, parser version, `container_count`, ordered nonempty/empty containers as present in the source, deterministic `text_digest`, parse warnings, and container collection. `container_count` must agree with the collection.
- `DocumentContainer`: kind (`sheet` for this adapter; future-safe closed values may include `page`), name or number, zero-based order, ordered blocks.
- `ContentBlock`: kind (`text`, `table`, `image`, `attachment`), zero-based order, stable structural address, optional text/bbox, nonblank SHA-256 `content_hash`, and any table-cell collection required below.
- `TableCell`: row and column coordinates, A1 address, raw value, display value, formula/cached-formula information when available, and merged range.

All cross-field/cardinality/order invariants must validate on construction and on `model_copy(update=...)`. Provide a deterministic `ReportDocument.find_cell(sheet_name, address)` or equivalent public lookup used by tests and later rule evaluation; missing/duplicate lookups must fail predictably.

## XLS behavior

- `XlsParser.parse(staged: StagedFile) -> ReportDocument` accepts only `detected_format == "XLS"` and verifies the staged payload still matches its recorded SHA-256/size before parsing.
- Use `xlrd` to preserve workbook sheet names/order, used cell region, raw/cached displayed values, cell row/column, A1 address, and merged cells. Do not recalculate formulas; if cached/display content is unavailable, add a parse warning rather than inventing a result.
- Use `olefile` read-only inspection to inventory embedded streams/objects as `image` or `attachment` blocks where safely identifiable. Do not execute macros, scripts, external links, or embedded programs. Unknown OLE objects remain opaque evidence with locator/order/hash rather than guessed content.
- Cell structural address format is exactly `sheet:<zero-based-index>:<percent-escaped-name>/cell:<A1>`. Object addresses use the same sheet prefix where association is knowable; otherwise use a deterministic workbook-level address.
- Hash normalized display text using SHA-256. Normalize only line endings and surrounding whitespace consistently; do not alter semantic content.
- `text_digest` must be deterministic across repeated parses of the same staged file and ordered content.
- Return stable parser errors/codes for wrong format, changed staged file, unreadable/corrupt workbook, and unsupported/encrypted content as applicable.

## Parser registry

- `ParserRegistry` registers parsers by normalized uppercase format and returns one through `for_format(format)`.
- Duplicate registration and missing format produce stable, tested errors.
- Registry dispatch does not inspect file extensions and does not contain format-specific parsing logic.

## Required tests

Write tests first and record actual RED. Cover at least:

1. A contract fake parser returns a valid normalized document whose source ID matches, containers are ordered, every block has a 64-character SHA-256 hash, and immutable/cross-field invariants reject malformed documents.
2. A small deterministic XLS fixture contains multiple sheets, a nonempty `B2` displaying `结论`, and merged range `B2:C2`; assert sheet order, lookup, raw/display value, structural address, merge address, hash determinism, and repeated-parse text digest.
3. Empty cells/sheets do not create invented text; numeric/date/boolean/error/formula-cache cases are represented faithfully or carry explicit warnings according to what `xlrd` exposes.
4. Wrong staged format, staged hash/size mutation, corrupt XLS, duplicate/missing registry entries return stable errors.
5. OLE inventory is deterministic and does not open/execute embedded content; an opaque object still has kind/order/address/hash.
6. Full prior backend suite remains green.
7. Real S-01 proof:
   - source path exactly `D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表\HPYR2D\DS\HYR2D DS Project Hardware Test Report（DVB-C for Overseas）V1.23-0327.xls`;
   - record source fingerprint before staging and after parsing and assert equality;
   - stage into a repository-local task temp directory and parse only the copy;
   - assert at least one sheet and at least one nonempty cell, not business correctness;
   - record sheet count, nonempty-cell count, embedded-object count, duration, and original fingerprint;
   - parse plus structural extraction must finish within 20 minutes;
   - clean the generated task workspace with `WorkspaceCleaner` after evidence capture.

A test-only XLS writer dependency is allowed only if declared and used solely to create deterministic fixtures. Do not rely on Microsoft Excel for synthetic fixtures.

## Commands and report

Use bundled Python and repository-local fresh `--basetemp`. Run focused unit/integration tests, then the entire backend suite.

`task-4-report.md` must record RED/GREEN commands and counts, exact files, parser/version details, synthetic fixture facts, S-01 metrics and duration, source before/after fingerprints, cleanup proof, and unresolved limitations. Explicitly state no Git commit exists.

## Completion gate

Task 4 is not complete until focused and full tests pass, S-01 is parsed only from its staged copy under 20 minutes with unchanged source fingerprint, cleanup succeeds, and the independent review package can verify all evidence.
