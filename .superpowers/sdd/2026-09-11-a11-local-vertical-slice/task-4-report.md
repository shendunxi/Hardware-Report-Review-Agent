# Task 4 Report — normalized document contract and XLS adapter

## Outcome

Task 4 implements the immutable normalized document contract, format-only parser registry, and read-only legacy XLS adapter. The adapter accepts only a verified `StagedFile` whose detected format is `XLS`, rechecks staged size and SHA-256, reads BIFF content from bytes with `xlrd`, and inventories every non-core OLE stream read-only with `olefile`. It does not recalculate formulas, execute embedded content, call Microsoft Office, or make business-correctness claims.

No Git commit exists, per the user constraint.

## TDD evidence

Bundled interpreter used for every command:

`C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`

Initial RED command, run from `backend/`:

`python -m pytest tests/unit/test_parser_contract.py tests/integration/test_xls_parser.py -v --basetemp=.pytest-tmp/task4-red-1`

Observed RED: collection failed with exactly 2 expected import errors because `ContentBlock`/the normalized models and `hw_review.parsers` did not yet exist; 0 tests were collected.

Implementation-cycle evidence:

- First executable implementation run: 13 collected, 6 passed, 7 failed. The failures exposed one invalid synthetic sheet name, one duplicate-test construction problem, and the remaining stable-error path.
- Second implementation run: 13 collected, 12 passed, 1 failed. The remaining failure showed that a non-OLE corrupt payload needed deterministic `CORRUPT_WORKBOOK` classification before `xlrd` dispatch.
- First GREEN: 13/13 passed, including S-01.
- Final focused command: `python -m pytest tests/unit/test_parser_contract.py tests/integration/test_xls_parser.py -v -s --basetemp=.pytest-tmp/task4-focused-final`
- Final focused result: 15/15 passed in 0.72 seconds.
- Full regression command: `python -m pytest -v --basetemp=.pytest-tmp/task4-full-final`
- Full regression result: 105/105 passed in 15.15 seconds.
- Import/bytecode verification: `python -m compileall -q src` passed.

### Independent-review fix round 1/5

Four Important findings were independently reproduced before changes and handled with separate TDD cycles:

1. Normalized identity RED: the unit suite failed collection because the requested shared, non-circular `hw_review.domain.hashing` layer did not exist. GREEN after adding canonical text/ordered identity helpers and construction/copy invariants: 7/7 unit contract tests passed. A further deceptive same-prefix cell locator test failed 1/1 before exact locator validation and passed 1/1 after it.
2. Out-of-range XLS date RED: a real `xlwt` fixture containing date-formatted numeric value `4000000` failed 1/1 with leaked `OverflowError`. GREEN: 1/1 passed with raw value/display retained and cell-scoped `DATE_VALUE_OUT_OF_RANGE` warning.
3. OLE fallback RED: an unfamiliar `Custom/Mystery` stream was omitted, so the target test failed 1/1 (`1 != 2`). GREEN: 1/1 passed after excluding only known core workbook/property streams and retaining every other stream as opaque evidence.
4. Failure-safe cleanup RED: injected post-copy staging and source-fingerprint failures left UUID task directories; the matrix produced 2 failed and 2 passed. GREEN: all 4/4 injected stage/parser/fingerprint/assertion failures cleaned the task directory and preserved the source fingerprint.

Fix-round focused command:

`python -m pytest tests/unit/test_parser_contract.py tests/integration/test_xls_parser.py -v -s --basetemp=.pytest-tmp/task4-fix1-focused`

Fix-round focused result: 22/22 passed in 0.84 seconds, including S-01.

Fix-round full command:

`python -m pytest -q --basetemp=.pytest-tmp/task4-fix1-full`

Fix-round full result: 112/112 passed in 17.55 seconds.

Final completion verification after the exact sheet-cell locator hardening:

- Focused Task 4: 22/22 passed in 0.85 seconds.
- Full backend: 112/112 passed in 17.69 seconds.
- `python -m compileall -q src`: exit 0.

## Files

Created:

- `backend/src/hw_review/parsers/__init__.py`
- `backend/src/hw_review/parsers/base.py`
- `backend/src/hw_review/parsers/xls.py`
- `backend/src/hw_review/domain/hashing.py`
- `backend/src/hw_review/services/parsing.py`
- `backend/tests/unit/test_parser_contract.py`
- `backend/tests/integration/test_xls_parser.py`
- `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-4-report.md`

Modified:

- `backend/src/hw_review/domain/models.py`
- `backend/src/hw_review/domain/__init__.py`
- `backend/pyproject.toml`

No staging, cleanup, persistence, requirements, design, plan, prototype, or prior test file was modified.

## Contract and adapter facts

- Added immutable `ParseWarning`, `TableCell`, `ContentBlock`, `DocumentContainer`, and `ReportDocument` models. Construction and `model_copy(update=...)` revalidate container counts, contiguous zero-based ordering, cell address/coordinate agreement, merge-master addresses, cell uniqueness, structural-address uniqueness, and SHA-256 shape and identity.
- Shared domain hashing validates cell hashes against normalized display text, table hashes against ordered cell structural identities, text-block hashes against normalized text, and document digests against ordered block identities. Sheet containers bind every sheet block and cell to the exact percent-escaped name/order prefix; only opaque `workbook/object:` image/attachment locators bypass the sheet prefix.
- `ReportDocument.find_cell(sheet_name, address)` returns exactly one matching cell and otherwise raises stable `CELL_NOT_FOUND` or `DUPLICATE_CELL` lookup errors.
- Cell addresses use exactly `sheet:<zero-based-index>:<percent-escaped-name>/cell:<A1>`.
- Workbook-level opaque OLE entries use deterministic `workbook/object:<percent-escaped-stream-path>` addresses.
- Text hashing changes only CRLF/CR to LF and strips surrounding whitespace before UTF-8 SHA-256.
- Parser identity recorded in documents: `xlrd-2.0.2+olefile-0.47/v1`.
- Runtime parser libraries verified: `xlrd 2.0.2`, `olefile 0.47`.
- Test-only deterministic XLS writer: `xlwt 1.3.0`, declared only in the `test` optional dependency set.
- Stable parser failure codes covered: `WRONG_FORMAT`, `STAGED_FILE_CHANGED`, `CORRUPT_WORKBOOK`, and `UNSUPPORTED_OR_ENCRYPTED`.
- Stable registry failure codes covered: `DUPLICATE_PARSER` and `PARSER_NOT_FOUND`; registry dispatch normalizes uppercase format names and never examines file extensions.

## Synthetic fixture facts

The deterministic fixture contains two sheets in source order: `Sheet 1 中文` and `Empty`. `B2:C2` is merged with master/display value `结论`; other cells cover number, boolean, date, and a formula whose formula text/cache identity is not exposed by `xlrd`. Tests also cover a sparse `J10`, an `xlrd` error cell displayed as `#DIV/0!`, a real date-formatted value `4000000`, repeat-parse hashes/digests, staged size/hash mutations, corrupt payloads, encrypted errors, registry failures, unfamiliar opaque OLE streams, and non-execution behavior.

## S-01 read-only proof

Source used exactly:

`D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表\HPYR2D\DS\HYR2D DS Project Hardware Test Report（DVB-C for Overseas）V1.23-0327.xls`

An outer failure-safe guard covers initial fingerprinting, staging, staged-path assertions, parsing, structural assertions, and post-parse fingerprinting. A nested `finally` guarantees `WorkspaceCleaner` runs even if fingerprint validation itself fails. The test copied S-01 with `FileStager` into repository-local `.task-work/task-4-s01/<task-uuid>/input/`, parsed only `staged.path`, and verified the source fingerprint before and after.

| Evidence | Value |
|---|---:|
| Source SHA-256 before | `0af1304d75481bbe525a7e831752dd42a177e997f39ff1588626985c698db08c` |
| Source SHA-256 after | `0af1304d75481bbe525a7e831752dd42a177e997f39ff1588626985c698db08c` |
| Source bytes before/after | `14,767,104` |
| Source mtime ns before/after | `1777446618000000000` |
| Sheet count | `18` |
| Non-empty normalized cell count | `6,358` |
| Non-core opaque embedded-object/stream blocks | `82` |
| Stage + parse + structural extraction duration | `0.490101300063543` seconds |
| Performance gate | PASS; less than 1,200 seconds |
| Source fingerprint equality | PASS |
| UUID task workspace removed | PASS |

These figures establish structural read compatibility only. They do not establish A11 rule correctness or historical report correctness.

## Cleanup proof

- The S-01 harness calls `WorkspaceCleaner.clean_task(task_id)` from the innermost failure-safe `finally` and asserts the generated UUID task directory no longer exists.
- Four injected-failure cases prove the same cleanup and source-preservation behavior for post-copy staging failure, parser failure, fingerprint failure, and acceptance assertion failure.
- Inspection after the final run found no entries below `.task-work/task-4-s01/`.

## Unresolved limitations

- `xlrd` exposes cached cell values but not original formula text or a reliable formula-cell identity. The adapter therefore never recalculates or invents formulas and emits `FORMULA_METADATA_UNAVAILABLE` as an explicit parse warning.
- Numeric/date `display_value` is deterministic and semantically normalized; it is not an Excel-rendered reproduction of every custom number format. The raw BIFF value is retained.
- OLE inventory excludes only known core workbook/property streams and records every other stream as opaque evidence, classifying an image only from a safe filename/stream-name signal. It does not OCR images, interpret payload semantics, execute macros/programs, or guess a sheet association when none is available.
- XLSX, DOC, DOCX, PDF, OCR, rules, API, and UI remain outside Task 4.
