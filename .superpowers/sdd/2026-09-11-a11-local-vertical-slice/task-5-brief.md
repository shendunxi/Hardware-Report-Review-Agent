# Task 5 Brief — PDF adapter and isolated Microsoft Word worker for DOC/DOCX

## Objective

Implement normalized PDF parsing and safe DOC/DOCX conversion through a short-lived child process that alone owns Microsoft Word COM. Prove read-only behavior on S-06, S-07, and S-14, including stable failures, page/structure evidence, duration, peak memory, original fingerprints, and task-workspace cleanup.

## Source of truth

- Plan: `docs/superpowers/plans/2026-09-11-a11-local-vertical-slice.md`, Task 5.
- Design: `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md`, sections 4.2, 5.1, 5.3, 5.4, 9, and 10.
- Sample catalog: `docs/requirements/a11-validation-sample-catalog-v0.1.md`, S-06, S-07, and S-14.
- Task 2 staging/cleanup and Task 4 normalized models/parser registry.

## Binding boundaries

- No Git.
- Real samples are read-only and must be parsed only from `FileStager` copies. Never write beside or save changes to originals.
- Microsoft Word is guaranteed on the development/test machine. Discover and record the actual runtime version; do not assume a version.
- Only the child worker process may initialize COM or hold a Word Application object. The FastAPI/main/parser process must not import or instantiate long-lived COM.
- Word must be invisible, macros force-disabled, alerts suppressed, links not updated, files opened read-only and not added to recent files, and documents closed without saving. Word must be quit in every normal/failure path.
- A worker timeout must terminate the worker and its owned child process tree, then return stable `DOC_CONVERSION_TIMEOUT`; conversion/open/dialog failures return `DOC_CONVERSION_FAILED`.
- DOC conversion produces a PDF visual copy plus filtered HTML and structured JSON metadata inside the task directory. Intermediates never replace the original staged identity.
- No OCR. Image-only PDF pages produce explicit `IMAGE_ONLY_PAGE` warnings and can never be interpreted as compliant content.
- Do not implement rules, LLM, API, UI, authentication, or production deployment.
- Strict TDD.

## Files

Create:

- `backend/src/hw_review/parsers/pdf.py`
- `backend/src/hw_review/parsers/doc.py`
- `backend/src/hw_review/parsers/word_worker.py`
- `backend/tests/integration/test_pdf_parser.py`
- `backend/tests/integration/test_doc_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-5-report.md`

Modify only as necessary:

- `backend/src/hw_review/parsers/__init__.py`
- `backend/src/hw_review/domain/models.py`, `domain/__init__.py`, and shared hashing helpers for a minimal conversion-provenance model/invariants.
- `backend/src/hw_review/services/parsing.py` only to register the new parsers without changing registry semantics.
- `backend/pyproject.toml` only for declared runtime/test dependencies already selected by the plan.

Do not modify requirements/design/plan, prototype, persistence/staging/cleanup implementations, or prior tests.

## PDF adapter behavior

- Use the supported `pymupdf` import, not the legacy `fitz` compatibility name.
- Accept only `detected_format == "PDF"`; verify staged bytes still match recorded size/SHA-256 before opening.
- Reject password-protected/encrypted PDF as `PDF_PROTECTED`; reject corrupt/unsupported PDF as `PDF_CORRUPT`; wrong format and changed staged copy use stable existing-style codes.
- Preserve source page order with one `DocumentContainer(kind="page", name_or_number=<1-based page>, order=<0-based>)` per page.
- Extract readable text blocks in deterministic visual order. Each text block has a 1-based `page:<n>/text:<order>` structural address, exact four-number bbox, normalized text, and validated SHA-256.
- Inventory every image occurrence without OCR. Record deterministic page/image address and bbox when available; hash safely extracted image bytes or a deterministic source-bound fallback. Do not invent image text.
- Extract table candidates when PyMuPDF can safely identify them; preserve cells/coordinates in the common table model without claiming semantic correctness. Failure of optional table discovery becomes a located warning, not a whole-document false success/failure.
- If a page has no readable non-whitespace text, attach `IMAGE_ONLY_PAGE` with that page address. A PDF with only image-only pages still returns structure plus warnings, never compliance.
- Document ID, block IDs, order, hashes, and `text_digest` are deterministic across repeated parses of the same staged file.

## Word worker contract

Provide:

- Immutable `ConversionArtifacts` containing original staged identity/hash, PDF path/hash, filtered HTML path/hash, structured JSON path/hash, discovered Word version, duration, peak child-process memory, and worker diagnostics needed by `DocParser`.
- `WordWorker.convert(input_path: Path, output_dir: Path, timeout_seconds: int) -> ConversionArtifacts`.
- Module CLI entry `python -m hw_review.parsers.word_worker` with a documented JSON or argument contract and machine-readable success/failure output.

Parent behavior:

- Launch with the same bundled Python executable and an argument list (no shell string).
- Generate/validate outputs strictly inside one system-generated task subdirectory; reject symlinks or paths escaping it.
- Capture stdout/stderr with bounded diagnostic length; nonzero/malformed output maps to `DOC_CONVERSION_FAILED`.
- On timeout, terminate the worker and its owned process tree without targeting unrelated Word instances; wait/reap it and remove incomplete outputs.
- Validate every returned artifact path, existence, size/hash, and original input hash before accepting it.

Child behavior:

- Initialize/uninitialize COM in the child only and import `pythoncom`/`win32com` only inside child execution paths.
- Configure `Visible=False`, `DisplayAlerts=0`, `AutomationSecurity=3` (`msoAutomationSecurityForceDisable`).
- Open with `ReadOnly=True`, `AddToRecentFiles=False`, `UpdateLinks=0`/false, no link refresh, and no conversion UI.
- Export PDF, filtered HTML, and deterministic UTF-8 JSON structure containing paragraphs and tables with stable indices, page numbers where Word exposes them, and text/cell data. Do not execute embedded content.
- `Document.Close(SaveChanges=0)` and `Application.Quit(SaveChanges=0)` in nested `finally` blocks. A failed close/quit must not hide the primary error but must be reported diagnostically.

## DOC/DOCX adapter behavior

- Accept staged `DOC` and `DOCX`; real acceptance in this task is DOC only because no real DOCX sample exists. Report DOCX as contract-tested/unverified on real samples.
- Reverify staged source size/hash; derive conversion output under the same UUID task directory, never beside the original.
- Invoke only the `WordWorker` contract. Normalize structured paragraph/table records into page containers and blocks; use the PDF visual copy to establish/validate page inventory and image-only warnings.
- Structural addresses must combine 1-based page plus paragraph/table indices (and table-cell address where applicable). Conversion provenance must retain original source SHA-256 and all conversion artifact SHA-256 values so later evidence can trace the derivation.
- Stable failures: `WRONG_FORMAT`, `STAGED_FILE_CHANGED`, `DOC_CONVERSION_TIMEOUT`, `DOC_CONVERSION_FAILED`, `DOC_ARTIFACT_INVALID`.
- Clean incomplete conversion outputs on all failures. Successful artifacts remain until task completion/acceptance cleanup.

## Required tests

Write actual RED first. Cover at least:

### PDF

1. Generated text PDF yields page container, text block with page address/bbox/hash, deterministic IDs/digest, and exact source ID.
2. Generated image-only page yields an image block and located `IMAGE_ONLY_PAGE`; no invented text.
3. Multi-page ordering, multiple text blocks/images, and optional table-candidate warnings are deterministic.
4. Changed staged payload, wrong format, encrypted PDF, corrupt PDF, and malformed image extraction return stable behavior.

### Word/DOC

5. A fake COM/application boundary proves `Visible=False`, alerts off, automation security force-disable, `ReadOnly=True`, `AddToRecentFiles=False`, `UpdateLinks=0`, close-without-save, quit, and COM uninitialization on success and injected failure.
6. A fake subprocess worker proves command uses list/no shell, malformed/nonzero output mapping, bounded diagnostics, output path/hash validation, and incomplete-output cleanup.
7. A hanging worker proves timeout, owned-process-tree termination/reaping, `DOC_CONVERSION_TIMEOUT`, and no unrelated process targeting.
8. Fake conversion artifacts prove DOC normalization of paragraphs/tables/pages, source/provenance identity, deterministic hashes, and no direct COM in the parser process.
9. Output traversal/symlink/missing/hash-mismatch artifacts are rejected as `DOC_ARTIFACT_INVALID`.

### Real read-only acceptance

10. S-07 PDF and S-06/S-14 DOC are each fingerprinted before staging and after parse, parsed only from staged copies, timed under 20 minutes per file, measured for peak memory, and cleaned with nested failure-safe guards.
11. Each real input yields page/container inventory and either nonempty text or explicit located `IMAGE_ONLY_PAGE`. Record page/container/text/image/table counts without judging A11 correctness.
12. Injected parser/worker/fingerprint/assertion failures on synthetic fixtures prove cleanup cannot be bypassed.
13. Full prior backend suite remains green; compileall passes; no task-workspace remnants remain.

## Evidence report

`task-5-report.md` must record:

- exact RED/GREEN commands, exit codes, and counts;
- PyMuPDF version and discovered Word version;
- worker command/protocol, exit/timeout/kill/reap proof and COM safety flag evidence;
- S-06, S-07, S-14 source before/after fingerprints, bytes, page/container/text/image/table counts, duration, and peak memory;
- clear statement that DOCX lacks a real sample and cannot be claimed as real-compatible;
- cleanup/remnant proof, exact files, deviations/risks, and no Git commit.

## Completion gate

Task 5 is complete only when focused and full tests pass, real S-06/S-07/S-14 parse evidence satisfies the read-only/20-minute/diagnostic gates, Word exits or is safely terminated, all task workspaces are cleaned after evidence capture, and no real DOCX compatibility claim is made.
