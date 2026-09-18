# Task 5 Report — PDF adapter and isolated Word worker for DOC/DOCX

Date: 2026-09-15  
Implementation status: **implemented and contract-tested**  
Real-sample acceptance status: **NO-GO** (S-06/S-14 blocked because Microsoft Word is not installed/registered on this machine; WPS is not accepted as a substitute)

## 1. Delivered behavior

- `PdfParser` verifies the staged size/SHA-256, accepts only `PDF`, rejects changed/protected/corrupt inputs with stable codes, preserves page order, extracts normalized text blocks with page addresses and four-number bboxes, inventories each image occurrence without OCR, emits located `IMAGE_ONLY_PAGE`, and treats optional table discovery failure as a located warning.
- `DocParser` accepts a configured `DOC` or `DOCX` contract, verifies the staged source before and after conversion, validates the fresh conversion-attempt identity plus every returned path/size/SHA-256, normalizes paragraphs/tables/pages and every PDF image occurrence, and retains source/PDF/HTML/JSON conversion provenance.
- `WordWorker` uses an argument-list subprocess command with `shell=False`, creates a new unpredictable UUID attempt beneath `<task UUID>/conversion/<source UUID>/` for every call, rejects existing attempts and reparse-point components, and binds every returned artifact to that exact attempt by path, nonzero size, and SHA-256.
- Parent-side start/timeout failure handling preserves the stable primary code, bounds all termination diagnostics, falls back to `process.kill()` if owned-tree termination fails or the worker does not reap, uses finite five-second reap attempts, and cleans incomplete outputs in failure paths.
- Only the child execution path imports `pythoncom`/`win32com`. The child requests an invisible Office application, disables alerts and macros, opens read-only without recent-file insertion, blocks link updates, exports PDF/filtered HTML/deterministic JSON, closes without save, quits, and uninitializes COM in nested cleanup paths. The child failure envelope preserves the first conversion failure while reporting bounded Close/option-restore/Quit/CoUninitialize diagnostics.
- When an older Word type library rejects the `UpdateLinks` keyword, the worker temporarily sets `Options.UpdateLinksAtOpen=False`, retries, then restores the previous option before quitting.
- The production default refuses to launch when `Word.Application` is not registered to `WINWORD.EXE`; this prevents accidental substitution of Kingsoft WPS.

No A11 rule evaluation, LLM, API, UI, authentication, or deployment behavior was added.

## 2. TDD evidence

All commands used the bundled runtime:

`C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

| Phase | Command (from `backend/`) | Exit | Evidence |
|---|---|---:|---|
| Initial RED | `python -m pytest tests\integration\test_pdf_parser.py tests\integration\test_doc_parser.py -v` | 1 | 0 collected; 2 expected import errors because `pdf.py` and `doc.py` did not exist |
| First GREEN iteration | same focused suite with isolated `--basetemp` | 1 | 22 passed, 2 failed; exposed cross-format visual-order and repeated-artifact test-fixture issues |
| Base GREEN | same focused suite | 0 | 24 passed |
| Boundary RED | visual order + repeated image + parent artifact-code tests | 1 | 5 failed for the intended missing behaviors |
| Boundary GREEN | same five tests | 0 | 5 passed |
| Link-setting RED | `test_child_restores_word_link_option_when_open_keyword_is_unavailable` | 1 | prior link-update option remained modified |
| Link-setting GREEN | same test | 0 | 1 passed; original option restored |
| Image-fallback RED | `test_malformed_image_extraction_uses_deterministic_source_bound_hash` | 1 | expected missing helper failure |
| Image-fallback GREEN | same test | 0 | 1 passed; malformed image bytes use a deterministic source-bound hash |
| Cleanup failure injection | `test_task5_acceptance_cleanup_cannot_be_bypassed` | 0 | 4 passed for parser/worker/fingerprint/assertion failures |
| Fix 1 parent-failure RED | start OSError, terminator failure, and hung-reap cases | 1 | 3 intended failures before robust fallback/reap handling |
| Fix 1 parent-failure GREEN | same targeted cases, including terminator-success/hung-final-reap | 0 | 4 passed; every post-timeout reap used a finite timeout |
| Fix 2 fresh-attempt RED/GREEN | stale attempt, attempt reuse, empty artifact, size mismatch | 1 / 0 | 4 intended failures, then 4 passed |
| Fix 3 reparse RED/GREEN | parent/child symlink and Windows junction cases | 1 / 0 | Windows junction changed from failure to pass; two symlink cases honestly skipped because the current account lacks WinError 1314 privilege |
| Fix 4 cleanup-envelope RED | simultaneous export/Close/option-restore/Quit/Uninitialize failure | 1 | expected collection error because `ChildConversionFailure` did not yet exist |
| Fix 4 cleanup-envelope GREEN | cleanup-envelope plus COM boundary cases | 0 | 3 passed; primary export error retained and all four cleanup diagnostics present within 512 characters |
| Fix 5 image-occurrence RED/GREEN | reused image at two positions in converted DOC PDF | 1 / 0 | second occurrence initially reused the first bbox; then 1 passed with deterministic unique addresses/bboxes and identical payload hashes |
| Fix round 2 failure-envelope RED | structured nonzero child failure plus malformed-envelope cases | 1 | 2 intended failures: long stderr erased the primary/cleanup evidence and malformed structured failure had no stable message |
| Fix round 2 failure-envelope GREEN | same cases plus existing malformed/nonzero cases | 0 | 4 passed; structured primary and cleanup evidence survived before bounded stderr, malformed envelopes remained stable |
| Final focused | `python -m pytest tests\integration\test_pdf_parser.py tests\integration\test_doc_parser.py -q -rs --basetemp .pytest-tmp-task5-fix2-focused-final` | 0 | 48 passed, 4 skipped in 3.27 s: 2 unavailable-symlink privilege skips and 2 real-DOC Word-gate NO-GO skips |
| Final full backend | `python -m pytest -q -rs --basetemp .pytest-tmp-task5-fix2-full-final` | 0 | 160 passed, 4 skipped in 25.09 s with the same explicit skip reasons |
| Compile | `python -m compileall -q src tests` | 0 | no compilation errors |

PyMuPDF runtime version: **1.28.2**. The implementation imports `pymupdf`, not the legacy `fitz` name.

## 3. Worker protocol and isolation evidence

Parent command shape:

```text
[<same bundled python>, -m, hw_review.parsers.word_worker,
 --input, <staged task-local path>, --output-dir, <task-local conversion path>]
```

The child writes one JSON envelope to stdout. The supplied `--output-dir` is the exact fresh UUID attempt, not a reusable base:

- success: `{"ok": true, "artifacts": {...}}`
- failure: `{"ok": false, "code": "DOC_CONVERSION_FAILED", "message": "...", "diagnostics": [...]}`

Contract-test evidence:

- process invocation is a list and `shell=False`;
- every call creates a new UUID attempt with `exist_ok=False`; pre-existing stale valid files and even an existing empty attempt cannot be accepted;
- the raw output path and every existing parent component are inspected for symlink/junction/reparse behavior before resolution in both parent and child entries, followed by a separate resolved-containment check;
- success output is parsed and all source/artifact attempt IDs, paths, nonzero sizes, and hashes are revalidated;
- malformed/nonzero output maps to `DOC_CONVERSION_FAILED` with bounded diagnostics;
- on a nonzero exit, the parent first strictly validates the child failure envelope (`ok=false`, stable code, nonempty bounded message, string diagnostic list), preserves its primary code/message, budgets cleanup diagnostics ahead of stderr, and appends only the remaining bounded stderr tail as secondary context;
- malformed structured failure envelopes map to the stable `DOC_CONVERSION_FAILED` / `Word worker returned invalid failure envelope` result instead of exposing arbitrary stdout/stderr;
- missing, escaped, and hash-mismatched outputs map to `DOC_ARTIFACT_INVALID` and are removed;
- process-start `OSError` maps to `DOC_CONVERSION_FAILED`; timeout remains `DOC_CONVERSION_TIMEOUT` even when the owned-tree terminator, fallback kill, or final reap reports an additional failure;
- the hanging-process fake used PID `4242`; only `4242` was sent to the injected owned-tree terminator, every reap used a finite five-second grace timeout, fallback `process.kill()` was exercised, and the partial output directory was absent afterward;
- fake COM success and injected-open failure both proved `Visible=False`, `DisplayAlerts=0`, `AutomationSecurity=3`, `ReadOnly=True`, `AddToRecentFiles=False`, `UpdateLinks=0` (or the guarded/restored Word option fallback), `Close(SaveChanges=0)`, `Quit(SaveChanges=0)`, and final COM uninitialization;
- simultaneous export, Close, option restore, Quit, and CoUninitialize failures retained `RuntimeError: injected primary export failure` as the primary message while recording all cleanup failures in the bounded diagnostic list;
- a converted-PDF fixture that reuses one image xref at two positions produced exactly two image blocks, ordered by visual bbox with addresses `page:1/image:1` and `page:1/image:2`, distinct bboxes, and the same payload hash;
- final process scan found `NO_WORD_WORKER_PROCESS`.

## 4. Real read-only acceptance evidence

### S-07 — PDF — PASS

Source: `D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表\TCY30\PP\TCY30 (903442) PP 可靠性测试报告_20260609.pdf`

| Metric | Result |
|---|---:|
| Bytes | 3,139,592 |
| SHA-256 before | `62673cba8b9fce52ba90cf42f5faa5b5949c6cc26b7151863c1951c652934ffd` |
| SHA-256 after | same |
| mtime ns before/after | `1780992956671172900` / same |
| Pages/containers | 55 |
| Text blocks | 627 |
| Image occurrences | 94 |
| Table candidates | 46 |
| Parse duration | 1.1252 s |
| Peak process memory | 152,338,432 bytes |

The file was staged through `FileStager`, parsed only from the copy, finished below 20 minutes, and its UUID task workspace was removed in the nested `finally` path.

### S-06 — DOC — NO-GO

Source: `D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表\TCY30\PP\TCY30 (903442) PP 可靠性测试报告_20260609.doc`

| Metric | Result |
|---|---:|
| Bytes | 25,950,107 |
| SHA-256 before | `1847231157ce3509de133fd19bdff3988fb147da47cd6578b068d5f33c8cfa46` |
| SHA-256 after | same |
| mtime ns before/after | `1780992928394000000` / same |
| Page/container/text/image/table counts | not available — Microsoft Word gate failed before accepted conversion |
| Duration/peak child memory | not accepted — no Microsoft Word worker ran to completion |

An earlier failure-safe attempt staged the file, invoked the isolated child, received a Kingsoft WPS conversion failure, and removed the UUID task directory. The final guarded acceptance probe fingerprints the source before/after and skips with NO-GO before launching the non-Microsoft server.

### S-14 — DOC — NO-GO

Source: `D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表\TFY03\PP\TFY03 (903047) PP 可靠性测试报告_20240920.doc`

| Metric | Result |
|---|---:|
| Bytes | 10,613,760 |
| SHA-256 before | `38f750860a298042bda88c2ef478be58651ba352c86a00ce52a2145413cc2380` |
| SHA-256 after | same |
| mtime ns before/after | `1726821501998000000` / same |
| Page/container/text/image/table counts | not available — Microsoft Word gate failed before accepted conversion |
| Duration/peak child memory | not accepted — no Microsoft Word worker ran to completion |

The same failure-safe staging/cleanup and final guarded fingerprint behavior as S-06 was observed.

## 5. Microsoft Word gate evidence

- `Word.Application` CLSID: `{000209FF-0000-0000-C000-000000000046}`.
- 32-bit `LocalServer32`: `C:\PROGRA~2\Kingsoft\WPS Office\12.8.2.18581\office6\wps.exe /Automation`.
- Registered product: `WPS Office`.
- Registered company: `Zhuhai Kingsoft Office Software Co.,Ltd`.
- Registered product version: `12,8,2,18581`.
- Common Microsoft Office16 `WINWORD.EXE` installation paths were absent.
- Therefore a Microsoft Word runtime version could not be discovered. The actual registered substitute is WPS Office 12.8.2.18581, which is outside the binding acceptance boundary.

A `wps.exe` process with PID `35800` was observed, but its start time was `2026-09-09 10:51:15`, predating this Task 5 execution. It was treated as unrelated and was not targeted, which preserves the “owned process tree only” safety boundary.

## 6. Cleanup/remnant proof

- Synthetic parser, worker, fingerprint, and assertion failure injections all removed the relevant UUID task directory.
- S-07 acceptance removed its staged input and all parser outputs after evidence capture.
- Failed S-06/S-14 attempts removed staged inputs and partial conversion directories.
- Final scan: `NO_TASK5_WORKSPACE_REMNANTS`.
- Final scan: `NO_WORD_WORKER_PROCESS`.
- Twenty-three fix-round Task-5-only pytest base directories were resolved under the exact repository root or `backend/`, verified as direct children with the `.pytest-tmp-task5-*` prefix, and removed; zero remained.
- An unrelated pre-existing `.task-work/task-4-s01` directory was preserved.

## 7. Exact files created or modified

Created:

- `backend/src/hw_review/parsers/pdf.py`
- `backend/src/hw_review/parsers/doc.py`
- `backend/src/hw_review/parsers/word_worker.py`
- `backend/tests/integration/test_pdf_parser.py`
- `backend/tests/integration/test_doc_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-5-report.md`

Modified:

- `backend/src/hw_review/parsers/__init__.py`
- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`

No requirements, design, plan, prototype, persistence, staging, cleanup, prior tests, or Git state was modified. No Git commit was created.

## 8. Deviations, risks, and final gate

- Real DOC/DOCX compatibility is **not accepted** because the required Microsoft Word runtime is unavailable. Installing/registering Microsoft Word and rerunning S-06/S-14 is mandatory before Task 5 can be marked fully accepted.
- DOCX is contract-tested with synthetic conversion artifacts only. There is no real DOCX sample, so no real-compatible claim is made.
- PDF table discovery identifies candidates only; it does not claim semantic correctness. PyMuPDF emitted an advisory suggesting `pymupdf_layout`; no additional package was added because it is outside the frozen dependency plan.
- The implementation portion and full regression suite are green, but the binding completion gate requires successful real S-06/S-14 conversion. **Task 5 overall remains NO-GO / acceptance blocked.**
