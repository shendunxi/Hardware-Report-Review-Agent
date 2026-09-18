# A11 本地真实解析与规则审核纵向切片实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个在 Windows 开发机本地运行的端到端版本，能够只读解析现有 17 个真实样本、执行 A11 的 21 个校验项、保存可追溯证据，并将真实任务接入已确认的审核界面。

**Architecture:** FastAPI 提供同源 API 和静态前端；格式专用适配器把 XLS、DOC、PDF 转换为统一报告模型；确定性 A11 规则引擎生成系统初判和证据；SQLite 保存任务、规则结果、人工决定与修订快照，文件本体保存在任务级目录并按生命周期清理。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy 2、Alembic、SQLite、xlrd、olefile、PyMuPDF、pywin32、psutil、pytest、现有原生 HTML/CSS/JavaScript 与 Node test runner。

**Spec:** `docs/superpowers/specs/2026-09-11-a11-local-vertical-slice-design.md`

## Global Constraints

- 不初始化、配置或使用 Git；每项任务用测试输出和 `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/` 下的报告留痕。
- 样本根目录固定为 `D:\Document\AI创新应用大赛\硬件测试报告审核智能体\硬件测试报告及检查表`；样本只读，任何阶段不得修改内容、大小、哈希或最后修改时间。
- 开发数据库固定使用 SQLite；生产数据库保持待定，不加入 PostgreSQL 专属实现。
- 本阶段不调用大语言模型、不执行 OCR、不生成正式 XLS、不实现真实账号权限和模板管理后端。
- 22 个 A11 源行中只生成 21 个 `RuleResult`；TR-05 只作为 TR-04 的证据地址。
- 系统初判只允许 `COMPLIANT`、`NON_COMPLIANT`、`NOT_APPLICABLE`、`NEEDS_REVIEW`；人工最终状态只允许前三种。
- 必需外部证据缺失或客观硬性失败优先判 `NON_COMPLIANT`；不存在硬性失败但语义不能确定才判 `NEEDS_REVIEW`。
- 单文件解析加客观规则执行不得超过 20 分钟；必须记录解析耗时、规则耗时和峰值内存。
- 临时目录按任务隔离，完成或失败后立即清理，异常残留最迟 24 小时删除。
- 执行前通过工作区依赖发现能力解析 Python 绝对路径；若 `python` 不在 PATH，后续所有命令统一使用该绝对路径并在证据报告中记录。

## Planned File Structure

```text
backend/
  pyproject.toml
  alembic.ini
  src/hw_review/
    api/app.py
    api/errors.py
    api/routes/tasks.py
    config.py
    domain/enums.py
    domain/models.py
    domain/ports.py
    services/staging.py
    services/cleanup.py
    services/parsing.py
    services/evaluation.py
    services/lifecycle.py
    parsers/base.py
    parsers/xls.py
    parsers/doc.py
    parsers/pdf.py
    rules/a11_registry.py
    rules/a11_engine.py
    persistence/database.py
    persistence/tables.py
    persistence/repositories.py
  migrations/versions/0001_initial.py
  tests/
    unit/
    integration/
    acceptance/
prototype/a11-ui/
  api-client.js
  app.js
  index.html
  tests/prototype.test.js
docs/evidence/a11-local-vertical-slice/
```

---

### Task 1: Python 工程骨架与领域契约

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/hw_review/__init__.py`
- Create: `backend/src/hw_review/domain/__init__.py`
- Create: `backend/src/hw_review/config.py`
- Create: `backend/src/hw_review/domain/enums.py`
- Create: `backend/src/hw_review/domain/models.py`
- Create: `backend/src/hw_review/domain/ports.py`
- Create: `backend/tests/unit/test_domain_contracts.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-1-report.md`

**Interfaces:**
- Produces: `ReviewStatus`, `FinalStatus`, `TaskState`, `FileRole`, `EvidenceKind`; normalized Pydantic models; parser, repository and clock protocols consumed by all later tasks.

`EvidenceKind` 的精确值与设计一致：`JIRA_RECORD`、`PREVIOUS_STAGE_REPORT`、`POWER_RECORD`、`REQUIREMENT_OR_CASE_MAPPING`、`PAPER_RECORD`、`EMC_REPORT`、`TEMPERATURE_RECORD`、`AUTOMATION_RECORD`、`PUBLISHED_CRITERIA`、`OTHER`。

- [ ] **Step 1: Define dependency and test entry points**

Create `backend/pyproject.toml` with package name `hw-review`, Python floor `>=3.12`, runtime dependencies `fastapi`, `uvicorn`, `pydantic>=2`, `sqlalchemy>=2`, `alembic`, `python-multipart`, `xlrd`, `olefile`, `pymupdf`, `pywin32`, `psutil`, and test dependency `pytest`. Configure pytest with `pythonpath = ["src"]` and `testpaths = ["tests"]`.

- [ ] **Step 2: Write failing contract tests**

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

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/unit/test_domain_contracts.py -v` from `backend`.
Expected: FAIL because `hw_review.domain` contracts do not exist.

- [ ] **Step 4: Implement exact enums and models**

Define models with these stable fields:

```python
class SourceFileCreate(BaseModel):
    role: FileRole
    original_name: str
    evidence_kinds: tuple[EvidenceKind, ...] = ()

class EvidenceLocator(BaseModel):
    source_file_id: UUID
    container: str
    structural_address: str
    bbox: tuple[float, float, float, float] | None = None
    quoted_text: str | None = None
    content_hash: str

class AtomicResult(BaseModel):
    status: ReviewStatus
    basis_code: str
    basis_text: str
    evidence: tuple[EvidenceLocator, ...] = ()
    missing_materials: tuple[str, ...] = ()
    unresolved_semantics: tuple[str, ...] = ()
```

Add validators: exactly one primary report per task is enforced by the service contract; supporting files require at least one `EvidenceKind`; primary report has none.

- [ ] **Step 5: Run GREEN and full backend tests**

Run: `python -m pytest tests/unit/test_domain_contracts.py -v`.
Expected: PASS.

- [ ] **Step 6: Record task evidence**

Write the commands, pass counts, exact files and any deviations to `task-1-report.md`. Do not record Git SHAs.

---

### Task 2: 只读文件暂存、签名识别与安全清理

**Files:**
- Create: `backend/src/hw_review/services/staging.py`
- Create: `backend/src/hw_review/services/__init__.py`
- Create: `backend/src/hw_review/services/cleanup.py`
- Create: `backend/tests/unit/test_staging.py`
- Create: `backend/tests/unit/test_cleanup.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-2-report.md`

**Interfaces:**
- Consumes: `SourceFileCreate`, `FileRole`, `EvidenceKind` from Task 1.
- Produces: `FileStager.stage(source: Path, task_id: UUID, metadata: SourceFileCreate) -> StagedFile`; `WorkspaceCleaner.clean_task(task_id)`; `WorkspaceCleaner.clean_expired(now)`.

- [ ] **Step 1: Write failing staging tests**

```python
def test_stage_copies_without_mutating_source(tmp_path, ole_xls_fixture):
    before = fingerprint(ole_xls_fixture)
    staged = stager.stage(ole_xls_fixture, TASK_ID, PRIMARY_METADATA)
    assert staged.detected_format == "XLS"
    assert staged.sha256 == before.sha256
    assert fingerprint(ole_xls_fixture) == before
    assert staged.path.parent.name == "input"

def test_extension_signature_mismatch_is_rejected(tmp_path):
    fake = tmp_path / "report.pdf"
    fake.write_bytes(b"not a pdf")
    with pytest.raises(StageError) as error:
        stager.stage(fake, TASK_ID, PRIMARY_METADATA)
    assert error.value.code == "FILE_SIGNATURE_MISMATCH"
```

- [ ] **Step 2: Run staging tests RED**

Run: `python -m pytest tests/unit/test_staging.py -v`.
Expected: FAIL because `FileStager` and `fingerprint` are missing.

- [ ] **Step 3: Implement safe staging**

Recognize `%PDF-`, OLE Compound File (`D0 CF 11 E0 A1 B1 1A E1`) and OOXML ZIP signatures. Disambiguate OLE XLS/DOC by opening the compound directory and checking workbook/document streams. Generate storage names from UUIDs, use `shutil.copy2`, hash source and copy, and reject mismatch. Never combine user names into filesystem paths.

- [ ] **Step 4: Write cleanup tests RED**

```python
def test_cleanup_refuses_path_outside_workspace(cleaner, tmp_path):
    with pytest.raises(CleanupSafetyError):
        cleaner.remove_verified(tmp_path.parent)

def test_expired_cleanup_removes_only_task_directories(cleaner, task_dirs, now):
    removed = cleaner.clean_expired(now)
    assert removed == [task_dirs.expired_task_id]
    assert task_dirs.active.exists()
```

- [ ] **Step 5: Implement bounded cleanup and run GREEN**

Resolve both configured root and target with `Path.resolve()`, require `target.parent == work_root`, require a UUID directory name, and refuse symlinks. Run `python -m pytest tests/unit/test_staging.py tests/unit/test_cleanup.py -v`; expected PASS.

- [ ] **Step 6: Record task evidence**

Include a source-before/source-after fingerprint example and the cleanup safety assertions in `task-2-report.md`.

---

### Task 3: SQLite schema, migrations and lifecycle repository

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/versions/0001_initial.py`
- Create: `backend/src/hw_review/persistence/database.py`
- Create: `backend/src/hw_review/persistence/__init__.py`
- Create: `backend/src/hw_review/persistence/tables.py`
- Create: `backend/src/hw_review/persistence/repositories.py`
- Create: `backend/tests/integration/test_sqlite_repository.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-3-report.md`

**Interfaces:**
- Consumes: domain enums/models and repository protocols from Task 1.
- Produces: `SqliteTaskRepository`, `SqliteResultRepository`, `SqliteRevisionRepository`; migration command `python -m alembic upgrade head`.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_task_and_results_survive_repository_restart(db_url):
    first = repositories(db_url)
    first.tasks.create(task_fixture())
    first.results.replace_all(TASK_ID, twenty_one_results())
    first.close()
    second = repositories(db_url)
    assert second.tasks.get(TASK_ID).state == TaskState.READY_FOR_REVIEW
    assert len(second.results.list_for_task(TASK_ID)) == 21

def test_revision_snapshot_is_immutable_and_unique(repositories):
    revision = repositories.revisions.complete(TASK_ID, decisions())
    assert revision.revision_no == 1
    with pytest.raises(CompletedRevisionError):
        repositories.revisions.update_snapshot(revision.id, {})
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/integration/test_sqlite_repository.py -v`.
Expected: FAIL because persistence modules are absent.

- [ ] **Step 3: Implement schema and repository transactions**

Create tables for tasks, source files, parse artifacts, rule results, manual decisions, review revisions and stage failures. Store structured snapshots as JSON text through a repository serializer, not SQLite JSON operators. Enable foreign keys on every connection. Add unique constraints for `(task_id, rule_id, active_revision_no)` and `(task_id, revision_no)`.

- [ ] **Step 4: Apply migration to a temporary database**

Run: `python -m alembic -c alembic.ini upgrade head` with `HW_REVIEW_DATABASE_URL=sqlite:///./.tmp/migration-check.db`.
Expected: exit 0 and all seven tables present.

- [ ] **Step 5: Run GREEN and restart proof**

Run: `python -m pytest tests/integration/test_sqlite_repository.py -v`.
Expected: PASS, including closing and reopening a repository instance.

- [ ] **Step 6: Record task evidence**

Record migration version, schema inventory and test result in `task-3-report.md`.

---

### Task 4: Normalized parser contract and XLS adapter

**Files:**
- Create: `backend/src/hw_review/parsers/base.py`
- Create: `backend/src/hw_review/parsers/__init__.py`
- Create: `backend/src/hw_review/parsers/xls.py`
- Create: `backend/src/hw_review/services/parsing.py`
- Create: `backend/tests/unit/test_parser_contract.py`
- Create: `backend/tests/integration/test_xls_parser.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-4-report.md`

**Interfaces:**
- Consumes: `StagedFile` from Task 2 and normalized domain models from Task 1.
- Produces: `DocumentParser.parse(staged: StagedFile) -> ReportDocument`; `ParserRegistry.for_format(format) -> DocumentParser`; `XlsParser`.

- [ ] **Step 1: Write contract and XLS tests RED**

```python
def test_every_parser_returns_normalized_document(parser, staged_fixture):
    document = parser.parse(staged_fixture)
    assert document.source_file_id == staged_fixture.id
    assert document.containers
    assert all(block.content_hash for c in document.containers for block in c.blocks)

def test_xls_preserves_sheet_cell_and_merge_addresses(xls_parser, staged_xls):
    document = xls_parser.parse(staged_xls)
    assert document.containers[0].kind == "sheet"
    assert document.find_cell("Sheet1", "B2").display_value == "结论"
    assert document.find_cell("Sheet1", "B2").merged_range == "B2:C2"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/unit/test_parser_contract.py tests/integration/test_xls_parser.py -v`.
Expected: FAIL because parser modules are absent.

- [ ] **Step 3: Implement normalized document and XLS parsing**

Use xlrd for sheets/cells/merged ranges and cached formula display values. Use olefile only to inventory embedded streams; do not execute them. Build `structural_address` as `sheet:<index>:<escaped-name>/cell:<A1>` and hash normalized displayed text with SHA-256.

- [ ] **Step 4: Add real-sample focused test**

Use sample S-01 from the frozen catalog. Assert the parser returns at least one sheet and one non-empty cell, completes under 20 minutes, and the original fingerprint is unchanged. Do not assert business correctness from the historical workbook.

- [ ] **Step 5: Run GREEN**

Run: `python -m pytest tests/unit/test_parser_contract.py tests/integration/test_xls_parser.py -v`.
Expected: PASS.

- [ ] **Step 6: Record task evidence**

Record sheet counts, non-empty-cell counts, embedded-object counts, duration and source fingerprints in `task-4-report.md`.

---

### Task 5: DOC and PDF adapters with isolated Word worker

**Files:**
- Create: `backend/src/hw_review/parsers/doc.py`
- Create: `backend/src/hw_review/parsers/pdf.py`
- Create: `backend/src/hw_review/parsers/word_worker.py`
- Create: `backend/tests/integration/test_doc_parser.py`
- Create: `backend/tests/integration/test_pdf_parser.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-5-report.md`

**Interfaces:**
- Consumes: `DocumentParser`, `ReportDocument`, `StagedFile` from Tasks 1, 2 and 4.
- Produces: `DocParser`, `PdfParser`; `WordWorker.convert(input_path: Path, output_dir: Path, timeout_seconds: int) -> ConversionArtifacts`，由子进程入口 `python -m hw_review.parsers.word_worker` 调用。

- [ ] **Step 1: Write PDF tests RED**

```python
def test_pdf_locator_contains_page_bbox_and_hash(pdf_parser, staged_pdf):
    document = pdf_parser.parse(staged_pdf)
    block = next(b for c in document.containers for b in c.blocks if b.text)
    assert block.structural_address.startswith("page:")
    assert block.bbox is not None
    assert len(block.content_hash) == 64

def test_image_only_page_is_diagnostic_not_compliant(pdf_parser, image_pdf):
    document = pdf_parser.parse(image_pdf)
    assert "IMAGE_ONLY_PAGE" in document.parse_warnings
```

- [ ] **Step 2: Implement PDF adapter and run GREEN**

Use PyMuPDF block extraction. Preserve page number, block order and bounding boxes. Inventory image xrefs without OCR. Reject encrypted/corrupt files with `PDF_PROTECTED` or `PDF_CORRUPT`. Run `python -m pytest tests/integration/test_pdf_parser.py -v`; expected PASS.

- [ ] **Step 3: Write DOC worker tests RED**

```python
def test_doc_worker_opens_read_only_and_disables_macros(word_spy, staged_doc):
    DocParser(worker=word_spy).parse(staged_doc)
    assert word_spy.open_args.read_only is True
    assert word_spy.automation_security == "FORCE_DISABLE"
    assert word_spy.update_links is False

def test_doc_timeout_becomes_stable_error(hanging_worker, staged_doc):
    with pytest.raises(ParseError) as error:
        DocParser(worker=hanging_worker, timeout_seconds=30).parse(staged_doc)
    assert error.value.code == "DOC_CONVERSION_TIMEOUT"
```

- [ ] **Step 4: Implement isolated Word conversion**

Launch Word in a child process, set `AutomationSecurity` to force-disable macros, open with `ReadOnly=True`, `AddToRecentFiles=False`, `UpdateLinks=False`, export PDF and filtered HTML/structured metadata, close without saving, call `Quit`, and terminate the child after timeout. Ensure the main service never hosts a long-lived COM object.

- [ ] **Step 5: Run real DOC/PDF focused acceptance**

Parse S-06, S-07 and S-14. Assert each produces page/container inventory, non-empty text or an explicit `IMAGE_ONLY_PAGE` warning, source fingerprint stability, duration and peak-memory measurements. Run both adapter suites; expected PASS.

- [ ] **Step 6: Record task evidence**

Record Word version discovered at runtime, worker exit behavior, document/page counts, durations, memory and source fingerprints in `task-5-report.md`.

---

### Task 6: A11 registry, atomic checks and priority engine

**Files:**
- Create: `backend/src/hw_review/rules/a11_registry.py`
- Create: `backend/src/hw_review/rules/__init__.py`
- Create: `backend/src/hw_review/rules/a11_engine.py`
- Create: `backend/tests/unit/test_a11_registry.py`
- Create: `backend/tests/unit/test_a11_priority.py`
- Create: `backend/tests/unit/test_a11_rules.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-6-report.md`

**Interfaces:**
- Consumes: normalized `ReportDocument`, `SourceFile`, `EvidenceLocator`, `AtomicResult`.
- Produces: `A11Registry.source_rows() -> tuple[RuleDefinition, ...]`; `A11Registry.executed_rules() -> tuple[RuleDefinition, ...]`; `A11Engine.evaluate(task: ReviewInput) -> tuple[RuleResult, ...]`.

- [ ] **Step 1: Write registry tests RED**

```python
def test_a11_has_22_source_rows_and_21_executed_rules():
    assert len(A11Registry.source_rows()) == 22
    assert len(A11Registry.executed_rules()) == 21
    assert A11Registry.get("TR-05").enabled is False
    assert "TR-05" not in {r.id for r in A11Registry.executed_rules()}
```

- [ ] **Step 2: Write priority tests RED**

```python
@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([NOT_APPLICABLE, NOT_APPLICABLE], NOT_APPLICABLE),
        ([NEEDS_REVIEW, NON_COMPLIANT], NON_COMPLIANT),
        ([COMPLIANT, NON_COMPLIANT], NON_COMPLIANT),
        ([COMPLIANT, NEEDS_REVIEW], NEEDS_REVIEW),
        ([COMPLIANT, COMPLIANT], COMPLIANT),
    ],
)
def test_rollup_priority(statuses, expected):
    assert rollup(statuses).status == expected
```

- [ ] **Step 3: Run RED and implement registry/rollup**

Run the two focused files; expected missing modules. Encode the exact TR-01–TR-22 wording and main判定 type from `docs/requirements/template-check-rules-v0.1.md`. Implement the confirmed priority order and merge all evidence/missing/unresolved details without discarding lower-priority diagnostics.

- [ ] **Step 4: Write rule branch tests before each rule group**

Group implementation without changing IDs:

- Group A, deterministic structure/evidence: TR-01, TR-04, TR-07, TR-09, TR-10, TR-11, TR-19, TR-20, TR-21.
- Group B, deterministic subset plus unresolved semantics: TR-02, TR-03, TR-06, TR-08, TR-12, TR-14, TR-15, TR-22.
- Group C, AI-only this phase: TR-13, TR-16, TR-17, TR-18.

For every rule, write fixtures covering: required evidence missing → `NON_COMPLIANT`; objective failure with locator → `NON_COMPLIANT`; valid non-applicability when the rule allows it → `NOT_APPLICABLE`; unresolved semantics without hard failure → `NEEDS_REVIEW`; and `COMPLIANT` only where all applicable checks can be proven without LLM.

- [ ] **Step 5: Implement minimal document query helpers and rules**

Use exact helper signatures:

```python
class DocumentQuery(Protocol):
    def find_text(self, patterns: tuple[str, ...]) -> tuple[EvidenceLocator, ...]: ...
    def find_nonempty_labels(self, labels: tuple[str, ...]) -> dict[str, EvidenceLocator]: ...
    def has_evidence_kind(self, kind: EvidenceKind) -> bool: ...
```

No rule may search for a criterion that is absent from the frozen baseline. Missing published criteria route to missing-material or unresolved-semantic outcomes as specified per rule.

- [ ] **Step 6: Verify 21-result invariant**

Run: `python -m pytest tests/unit/test_a11_registry.py tests/unit/test_a11_priority.py tests/unit/test_a11_rules.py -v`.
Expected: PASS; each representative `ReviewInput` returns exactly 21 results and none has `rule_id == "TR-05"`.

- [ ] **Step 7: Record task evidence**

Create a matrix of rule ID, branch tests, evidence requirements and resulting states in `task-6-report.md`.

---

### Task 7: Task orchestration, lifecycle and FastAPI endpoints

**Files:**
- Create: `backend/src/hw_review/services/evaluation.py`
- Create: `backend/src/hw_review/services/lifecycle.py`
- Create: `backend/src/hw_review/api/errors.py`
- Create: `backend/src/hw_review/api/__init__.py`
- Create: `backend/src/hw_review/api/routes/tasks.py`
- Create: `backend/src/hw_review/api/app.py`
- Create: `backend/tests/integration/test_task_api.py`
- Create: `backend/tests/integration/test_lifecycle.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-7-report.md`

**Interfaces:**
- Consumes: staging, parser registry, A11 engine and SQLite repositories.
- Produces: `create_app(settings) -> FastAPI` and the seven endpoints frozen in design section 7.1.

- [ ] **Step 1: Write task API tests RED**

```python
def test_create_execute_and_fetch_real_task(client, xls_upload):
    created = client.post("/api/tasks", files=xls_upload).json()
    task_id = created["id"]
    assert created["state"] == "CREATED"
    assert client.post(f"/api/tasks/{task_id}/execute").status_code == 202
    detail = wait_for_state(client, task_id, "READY_FOR_REVIEW")
    assert len(detail["rule_results"]) == 21

def test_execute_is_idempotent(client, ready_task):
    client.post(f"/api/tasks/{ready_task}/execute")
    client.post(f"/api/tasks/{ready_task}/execute")
    assert len(client.get(f"/api/tasks/{ready_task}").json()["rule_results"]) == 21
```

- [ ] **Step 2: Write lifecycle tests RED**

Cover invalid manual final state, blank reason, TR-05 rejection, unresolved-pending completion rejection, successful completion, editing-completed rejection, reopen and two independent snapshots.

- [ ] **Step 3: Implement orchestration state transitions**

Persist a transition before and after each stage. Replace all 21 results in one transaction only after complete evaluation. On failure, persist `FAILED` with `stage`, `code`, `message`, `occurred_at`; do not leave a partial ready task.

- [ ] **Step 4: Implement endpoints and stable errors**

Return errors as:

```json
{
  "error": {
    "code": "UNRESOLVED_REVIEW_ITEMS",
    "message": "仍有待人工确认项",
    "details": {"remaining": 1}
  }
}
```

Serve `prototype/a11-ui` from the same FastAPI origin after API routes, so local execution requires no CORS relaxation.

- [ ] **Step 5: Run GREEN and restart recovery**

Run `python -m pytest tests/integration/test_task_api.py tests/integration/test_lifecycle.py -v`. Restart the app against the same temporary SQLite file and assert the task, 21 results, manual decisions and revisions remain readable.

- [ ] **Step 6: Record task evidence**

Record endpoint inventory, state transitions, error payloads, idempotency proof and restart recovery in `task-7-report.md`.

---

### Task 8: Connect the approved frontend to the real API

**Files:**
- Create: `prototype/a11-ui/api-client.js`
- Modify: `prototype/a11-ui/index.html`
- Modify: `prototype/a11-ui/app.js`
- Modify: `prototype/a11-ui/styles.css`
- Modify: `prototype/a11-ui/README.md`
- Modify: `prototype/a11-ui/tests/prototype.test.js`
- Create: `backend/tests/integration/test_static_frontend.py`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-8-report.md`

**Interfaces:**
- Consumes: Task 7 HTTP contracts.
- Produces: `ApiClient.createTask`, `executeTask`, `listTasks`, `getTask`, `saveManualDecision`, `completeTask`, `reopenTask`; real-mode UI at `/`.

- [ ] **Step 1: Write frontend contract tests RED**

Add Node tests that assert `index.html` loads `api-client.js` before `app.js`, demo mode is explicit, real mode never fabricates a task ID, supporting attachments require evidence-kind selections, stage failures render filename/stage/reason, and all state/count text comes from API payloads.

- [ ] **Step 2: Run RED**

Run: `node --test tests/prototype.test.js` from `prototype/a11-ui`.
Expected: new API tests fail while the existing 40 tests remain green.

- [ ] **Step 3: Implement API client and real upload**

Use `FormData` with one `primary_report`, zero or more `supporting_files`, and a JSON manifest pairing each supporting part with one or more exact `EvidenceKind` values. Display selected file names, formats and roles before submission. Preserve the current static demo under `?mode=demo`; default same-origin mode is real.

- [ ] **Step 4: Bind task and review screens**

Poll only while state is `FILES_STAGED`, `PARSING`, `PARSED` or `EVALUATING`, using a bounded two-second interval that stops on navigation, ready, failure or completion. Map API results to existing initial/final cards, filters, evidence blocks and completion gate. Do not expose a manual form for TR-05.

- [ ] **Step 5: Add failure/retry and simulation labels**

Display stable failure details and one retry action that calls `/execute`. Keep template management visibly simulated; keep the role selector labelled as a permission demonstration, not authentication.

- [ ] **Step 6: Run frontend and static-serving tests GREEN**

Run `node --check app.js`, `node --check api-client.js`, `node --test tests/prototype.test.js`, and `python -m pytest tests/integration/test_static_frontend.py -v`; expected all pass.

- [ ] **Step 7: Browser smoke test**

Start `python -m uvicorn hw_review.api.app:create_app --factory --host 127.0.0.1 --port 8766` from `backend`. In a real browser, upload one XLS sample, wait for 21 results, inspect one evidence locator, override a result with required reason, resolve pending items, complete, reopen and verify revision 2. Recheck 1440×900, 1280×720 and 760×900.

- [ ] **Step 8: Record task evidence**

Record browser states, viewport metrics, HTTP calls and automated counts in `task-8-report.md`.

---

### Task 9: Frozen 17-file acceptance harness and release gates

**Files:**
- Create: `backend/tests/acceptance/sample_manifest.json`
- Create: `backend/tests/acceptance/test_frozen_samples.py`
- Create: `backend/src/hw_review/acceptance/run_samples.py`
- Create: `backend/src/hw_review/acceptance/__init__.py`
- Create: `docs/evidence/a11-local-vertical-slice/sample-results.json`
- Create: `docs/evidence/a11-local-vertical-slice/sample-results.md`
- Create: `docs/evidence/a11-local-vertical-slice/release-gates.md`
- Create: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-9-report.md`

**Interfaces:**
- Consumes: all completed application modules and the exact S-01–S-17 catalog.
- Produces: command `python -m hw_review.acceptance.run_samples --manifest tests/acceptance/sample_manifest.json --output ../docs/evidence/a11-local-vertical-slice` and auditable GO/NO-GO evidence.

- [ ] **Step 1: Freeze the manifest**

Transcribe all 17 absolute paths, IDs and R-01–R-15 group IDs from `docs/requirements/a11-validation-sample-catalog-v0.1.md`. Store expected extension and one of `TASK_PRIMARY` or `COMPATIBILITY_ALTERNATE`. S-06 and S-14 (DOC) are the task primaries for paired groups R-06 and R-13; S-07 and S-15 (same-content PDF) are compatibility alternates. The remaining 13 files are task primaries, yielding exactly 15 business tasks and 17 parser inputs. Do not store an expected business verdict.

- [ ] **Step 2: Write acceptance assertions RED**

```python
def test_all_frozen_samples_are_readonly_and_parseable(sample_run):
    assert len(sample_run.files) == 17
    assert all(f.before == f.after for f in sample_run.files)
    assert all(f.parse_status == "SUCCESS" for f in sample_run.files)

def test_fifteen_report_groups_each_have_21_results(sample_run):
    assert len(sample_run.report_groups) == 15
    assert all(len(group.rule_results) == 21 for group in sample_run.report_groups)
    assert all("TR-05" not in {r.rule_id for r in group.rule_results}
               for group in sample_run.report_groups)
```

- [ ] **Step 3: Implement measurements and result schema**

For each file record format, bytes, SHA-256/size/mtime before and after, container/text/table/image counts, parse warnings, parse seconds, rule seconds, peak RSS MiB and error stage/code. For each report group record all 21 statuses, basis codes, evidence locator counts and missing/unresolved reasons.

- [ ] **Step 4: Run the complete sample matrix**

Run the acceptance command against the supplied root. Expected release result is GO only when G1–G8 from the design all pass. A diagnosed parse failure is useful evidence but still makes G2 NO-GO because the user-set target is 17/17 success.

- [ ] **Step 5: Verify source protection independently**

Rerun a separate fingerprint-only pass after the full matrix and compare with the pre-run snapshot. Any SHA-256, size or mtime change is a hard stop; do not rerun a mutating parser against the affected source.

- [ ] **Step 6: Run all automated suites**

Run:

```powershell
Set-Location 'E:\Coding\Hardware-Report-Review-Agent\backend'
python -m pytest -v
Set-Location 'E:\Coding\Hardware-Report-Review-Agent\prototype\a11-ui'
node --check app.js
node --check api-client.js
node --test tests/prototype.test.js
```

Expected: zero failures. Also scan product files for `无法判断|接受例外|严重性|A111` and report test-fixture matches separately.

- [ ] **Step 7: Write release gates and final review package**

`release-gates.md` must list G1–G8 individually as GO or NO-GO with links to `sample-results.json`, automated output and browser evidence. Explicitly repeat that real LLM, OCR, DOCX/XLSX compatibility, production database, authentication and formal XLS writing are unverified.

- [ ] **Step 8: Record task evidence**

Write final counts, failed gates, limitations and exact commands to `task-9-report.md`. Do not label the phase complete while any required gate is NO-GO.

---

## Final Review and Handoff

- [ ] Run a spec-compliance review across Tasks 1–9 using complete file review packages rather than Git diffs.
- [ ] Run a separate code-quality review for parser isolation, filesystem safety, transaction boundaries, evidence integrity and test realism.
- [ ] Fix Critical/Important findings with regression tests and rerun the affected acceptance gates.
- [ ] Keep `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/` because there is no Git history; it is the execution audit record.
- [ ] Deliver only the local vertical slice claims proven by G1–G8; do not promote deferred production capabilities.

## Plan Self-Review

- Spec coverage: sections 1–2 map to global constraints; sections 3–4 map to Tasks 1–4; section 5 maps to Tasks 2, 4 and 5; section 6 maps to Task 6; section 7 maps to Tasks 3 and 7; section 8 maps to Task 8; sections 9–10 map to Tasks 2, 5, 7 and 9; deferred items remain excluded by global constraints.
- Placeholder scan: no `TBD`, `TODO`, “implement later”, unspecified error-handling step or unnamed test step remains. Production database is explicitly deferred by the user and is not an implementation placeholder.
- Type consistency: `SourceFileCreate`, `StagedFile`, `ReportDocument`, `EvidenceLocator`, `AtomicResult`, `RuleResult`, `A11Registry`, `A11Engine`, repository interfaces and `ApiClient` methods are introduced before their consumers.
- Scope check: although the plan crosses parsers, rules, persistence and UI, they are coupled parts of one end-to-end vertical slice and culminate in one shared G1–G8 release decision; each task remains independently reviewable.
