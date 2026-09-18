# Task 2 report — read-only staging, signature detection, and bounded cleanup

## TDD evidence

### RED

Command, from `backend/`:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py tests/unit/test_cleanup.py -v
```

Exact summary: `collected 0 items / 2 errors`; both test modules failed collection with `ModuleNotFoundError: No module named 'hw_review.services'`. This was the expected missing-feature failure before any Task 2 production service existed.

During self-review, a second test-first cycle found that direct `StagedFile` construction did not yet enforce the role/evidence-kind invariant. Its RED command selected `test_staged_file_revalidates_role_and_evidence_kind_contract`; exact summary: `2 failed in 0.23s`, both with `Failed: DID NOT RAISE ValidationError`. Adding the model-level cross-field validator made both cases pass.

### GREEN — focused

The host's default pytest temp root was not readable (`PermissionError` under `C:\Users\sdt52153\AppData\Local\Temp\pytest-of-SDT52153`), so the successful run used a new, pre-checked task-specific `--basetemp` below the repository:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py tests/unit/test_cleanup.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-focused-final
```

Exact summary: `27 passed in 0.30s`.

### GREEN — full backend suite

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-full-final
```

Exact summary: `46 passed in 0.32s`.

## Independent-review fix round 1/5

Four Important findings were verified against the implementation and reproduced with tests before fixes.

### Review-fix RED

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix-red
```

Exact summary: `11 failed, 18 passed in 0.89s`. Failures proved that traversal/malformed/hostile task IDs could reach path handling, uppercase noncanonical UUID text was accepted, corrupt or manifest-less OOXML was accepted, a post-copy model failure left one payload, blank `original_name` was accepted, and no configurable/default size limit existed.

### Exact remediation

1. Task IDs are now accepted only as a `UUID` or canonical lowercase hyphenated UUID string. Coercion happens at the first line of `stage`, before task-specific filesystem work. The proposed task path is resolved and its parent is proven equal to the configured root before `mkdir`.
2. `SourceFileCreate.original_name` now has `min_length=1`; combined with the inherited whitespace stripping this rejects blank display names. Model construction is inside the post-copy protected region, and any exception after payload creation removes that payload and re-raises the original exception object.
3. OOXML detection now requires `[Content_Types].xml`, still identifies XLSX/DOCX from package entries, and calls `ZipFile.testzip()` before acceptance. Missing manifests and corrupt-member CRCs produce `CORRUPT_FILE`.
4. `FileStager` now has a positive configurable `max_file_size_bytes`. Its local-development default is `100 * 1024 * 1024` bytes (100 MiB). Size greater than the limit produces `FILE_TOO_LARGE` before signature detection, task-directory creation, or copy. The exact boundary remains accepted.

The 100 MiB value is an implementation default pending later API/configuration wiring; it is not a frozen production policy.

### Incremental GREEN

- Task-ID hostile input regressions: `4 passed, 25 deselected in 0.13s`.
- Blank metadata and residual-copy regressions: `2 passed, 27 deselected in 0.14s`.
- OOXML integrity regressions: `7 passed, 22 deselected in 0.30s`.
- File-size regressions: `3 passed, 26 deselected in 0.28s`.

### Final GREEN after review fixes

Focused command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py tests/unit/test_cleanup.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix-focused-green
```

Exact summary: `39 passed in 0.71s`.

Full backend command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix-full-green
```

Exact summary: `58 passed in 1.09s`.

All new filesystem effects remained under repository-local pytest temporary directories. No real sample was accessed and no Git commit exists by user constraint.

## Independent-review fix round 2/5

The re-review identified one Important resource-safety gap: `ZipFile.testzip()` verified CRCs by fully inflating members without configurable expansion limits.

### Review-fix RED

Primary RED command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix2-red
```

Exact summary: `10 failed, 31 passed in 0.68s`. The failures showed that archive ceilings were not accepted by `FileStager`, nonpositive OOXML limits were not validated, and the expansion/ratio boundary cases had no implementation.

A follow-up unreadable-member RED selected `test_unreadable_ooxml_member_is_mapped_to_stable_corrupt_error`; exact summary: `1 failed in 0.21s` because a synthetic `EOFError` escaped instead of becoming `CORRUPT_FILE`.

### Exact remediation

- Added configurable OOXML limits with local defaults of 10,000 members, per-member uncompressed bytes equal to `max_file_size_bytes`, aggregate uncompressed bytes equal to four times `max_file_size_bytes`, and a 100:1 compression ratio.
- All configured/resolved byte and count limits must be positive integers; compression ratio must be positive and finite. Validation occurs before creating the configured work root.
- Replaced `ZipFile.testzip()` with central-directory preflight followed by bounded reads of at most 1 MiB and never more than the remaining per-member or aggregate allowance plus one detection byte.
- Enforced member count, per-member size, aggregate size, per-member ratio, and aggregate ratio against declared metadata before inflation, then enforced byte ceilings and ratios again against actual bytes read.
- Every non-directory member is read through EOF, causing ZIP CRC verification. Declared and actual member/aggregate sizes must agree.
- Encrypted members and unreadable/truncated/unsupported-compression members return stable `CORRUPT_FILE`. Resource-ceiling violations return `ARCHIVE_RESOURCE_LIMIT_EXCEEDED`.
- All OOXML checks complete before task-directory creation or copying. Tests assert rejected archives leave no task directory.

The limits remain local implementation defaults pending later API/configuration wiring; they are not frozen production policy.

### Incremental GREEN

- Complete staging suite after initial fix: `41 passed in 0.58s`.
- Unreadable-member mapping after its focused fix: `1 passed in 0.12s`.

### Final GREEN after review fix round 2

Focused command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py tests/unit/test_cleanup.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix2-focused-final
```

Exact summary: `52 passed in 0.61s`.

Full backend command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix2-full-final
```

Exact summary: `71 passed in 1.15s`.

No real sample was accessed, all generated data stayed under repository-local pytest temporary directories, and no Git commit exists by user constraint.

## Independent-review fix round 3/5

The next re-review found that a malformed DEFLATE stream can raise `zlib.error`, which was not among the exceptions normalized to `CORRUPT_FILE`.

### Review-fix RED

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py::test_deflate_stream_error_is_mapped_to_stable_corrupt_error -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix3-red
```

The fixture created a real `ZIP_DEFLATED` OOXML member, replaced its compressed bytes while retaining the directory entry, and independently proved `ZipFile.read()` raises `zlib.error`. Exact RED summary: `1 failed in 0.28s`; the raw decoder exception escaped from the bounded member read.

### Remediation and GREEN

`zlib.error` is now mapped at the OOXML integrity boundary to the stable `StageError.code == "CORRUPT_FILE"`. The regression also asserts that no task directory exists after rejection.

Focused regression GREEN: `1 passed in 0.18s`.

Task 2 focused command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/unit/test_staging.py tests/unit/test_cleanup.py -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix3-focused-green
```

Exact summary: `53 passed in 0.59s`.

Full backend command:

```powershell
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -v --basetemp E:\Coding\Hardware-Report-Review-Agent\backend\.pytest-tmp\task2-review-fix3-full-green
```

Exact summary: `72 passed in 0.61s`.

No Git command was used and no real sample was accessed.

## Files created or modified

- Created `backend/src/hw_review/services/__init__.py`.
- Created `backend/src/hw_review/services/staging.py`.
- Created `backend/src/hw_review/services/cleanup.py`.
- Created `backend/tests/unit/test_staging.py`.
- Created `backend/tests/unit/test_cleanup.py`.
- Modified `backend/src/hw_review/domain/models.py` only to add the immutable validated `StagedFile` parser-input model.
- Modified `backend/src/hw_review/domain/__init__.py` only to export `StagedFile`.
- Created this report.

## Source immutability evidence

The focused test's synthetic OLE XLS source had the following fingerprint both before and after staging:

- SHA-256: `738ac19a64c9282adc2d3beacb5a3acf1799603515a4177223901d13750f4011`
- Size: `24` bytes
- Modification time: `1789348080908318500` ns

The staged payload hash and size matched those values. Its parent was the task's `input/` directory and its filename stem was its generated UUID, not the physical source name or the user-facing `original_name`.

## Cleanup safety and expiry evidence

The focused suite asserted that recursive cleanup refuses the configured root itself, an ancestor, an outside sibling, a nested path, a non-UUID direct child, and a UUID-named symbolic link. On this Windows host, creation of a real directory symlink was denied, so that branch used a narrow `Path.is_symlink` test double after the operating-system attempt failed; the external directory remained untouched.

The 24-hour expiry test created two exactly-expired UUID task directories, one active UUID task directory, one unrelated directory, and one unrelated file. The returned IDs were the two expired UUIDs in lexical UUID order; only those directories were removed. A separate test proved an explicitly configured two-hour threshold is honored. Every cleanup operation ran exclusively below pytest-created temporary directories under `backend/.pytest-tmp/`.

## Deviations and unresolved risks

- No real user sample was opened, copied, modified, or deleted in this task.
- OLE staging behavior is exercised with a synthetic OLE signature and a test double at the compound-directory inspection boundary because producing a valid compound file is outside this unit task. Production code uses `olefile.OleFileIO.listdir(streams=True, storages=False)` and recognizes only `Workbook`/`Book` versus `WordDocument`; real OLE compatibility remains a Task 4/5 acceptance concern.
- PDF recognition in this boundary checks the required `%PDF-` signature. Structural PDF readability belongs to the later parser adapter task.
- The host-global pytest temp permission issue required repository-local `--basetemp`; no production behavior changed because of it.
- No Git commit exists, by user constraint.
