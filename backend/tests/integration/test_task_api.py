"""Red/green contract coverage for the local task API."""

from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from collections.abc import Mapping
from pathlib import Path

import pytest
import fitz
from openpyxl import Workbook
import xlrd
import xlwt
from xlutils.copy import copy as copy_workbook


STALE_WORKSPACE_ID = "9e5a1c4b-6d2f-4a71-8c30-2f5b7d18a4e2"


class AsgiClient:
    """Small dependency-free ASGI contract client for this local service."""

    def __init__(self, app) -> None:
        self.app = app

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: Mapping[str, str] = {},
        client_host: str = "127.0.0.1",
    ):
        async def _call():
            messages = []
            sent = False

            async def receive():
                nonlocal sent
                if sent:
                    return {"type": "http.disconnect"}
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}

            async def send(message):
                messages.append(message)

            await self.app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": method,
                    "scheme": "http",
                    "path": path,
                    "raw_path": path.encode(),
                    "query_string": b"",
                    "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
                    "client": (client_host, 123),
                    "server": ("test", 80),
                },
                receive,
                send,
            )
            start = next(item for item in messages if item["type"] == "http.response.start")
            response_body = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
            response_headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in start.get("headers", [])
            }
            return start["status"], response_body, response_headers

        status, response_body, response_headers = asyncio.run(_call())
        return Response(status, response_body, response_headers)

    def post(self, path: str, *, files=None):
        if files is None:
            return self.request("POST", path)
        name, payload, content_type = files["primary_report"]
        boundary = "task-api-boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"primary_report\"; filename=\"{name}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        return self.request("POST", path, body=body, headers={"content-type": f"multipart/form-data; boundary={boundary}"})

    def post_multipart(self, path: str, parts: list[tuple[str, str | None, bytes | str, str | None]]):
        boundary = "task-api-boundary"
        body = bytearray()
        for field, filename, value, content_type in parts:
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"".encode())
            if filename is not None:
                body.extend(f"; filename=\"{filename}\"\r\nContent-Type: {content_type or 'application/octet-stream'}".encode())
            body.extend(b"\r\n\r\n")
            body.extend(value.encode() if isinstance(value, str) else value)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return self.request("POST", path, body=bytes(body), headers={"content-type": f"multipart/form-data; boundary={boundary}"})

    def get(self, path: str):
        return self.request("GET", path)

    def put(self, path: str, *, json: dict):
        return self.request("PUT", path, body=__import__("json").dumps(json).encode(), headers={"content-type": "application/json"})


class Response:
    def __init__(self, status_code: int, body: bytes, headers: dict[str, str]) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers

    @property
    def content(self) -> bytes:
        return self._body

    def json(self):
        return json.loads(self._body)


def _write_xls(path: Path) -> bytes:
    workbook = xlwt.Workbook()
    workbook.add_sheet("Report").write(0, 0, "阶段: PP")
    workbook.save(str(path))
    return path.read_bytes()


def _write_xlsx(path: Path) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "基本信息"
    sheet["A1"] = "Project stage"
    sheet["B1"] = "PP"
    sheet["A2"] = "Conclusion"
    sheet["B2"] = "PASS"
    workbook.save(path)
    workbook.close()
    return path.read_bytes()


def _write_pdf(path: Path) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Project stage: PP\nConclusion: PASS")
    document.save(path)
    document.close()
    return path.read_bytes()


def _write_a12_template(path: Path) -> Path:
    packaged = Path(__file__).resolve().parents[2] / "resources" / "a11" / "hardware-test-process-checklist-a11.xls"
    source = xlrd.open_workbook(packaged, formatting_info=True)
    writable = copy_workbook(source)
    writable.get_sheet(source.sheet_names().index("硬件测试过程检查表")).write(1, 0, "A12")
    writable.save(str(path))
    return path


@pytest.fixture
def client(tmp_path: Path):
    """Run an explicitly migrated local app; the application never creates schema."""
    from alembic import command
    from alembic.config import Config
    from hw_review.api.app import create_app
    from hw_review.config import Settings

    database = tmp_path / "review.db"
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    storage_root = tmp_path / "storage"
    # Seed one orphaned workspace past the TTL so the startup sweep must reclaim
    # it; on a fresh root a missing sweep call would pass unnoticed.
    stale_workspace = storage_root / STALE_WORKSPACE_ID
    (stale_workspace / "input").mkdir(parents=True)
    aged = time.time() - 3 * 24 * 60 * 60
    os.utime(stale_workspace, (aged, aged))
    app = create_app(Settings(database_url=f"sqlite:///{database.as_posix()}", storage_root=storage_root, auth_mode="disabled"))
    assert app.state.startup_reclamation == (STALE_WORKSPACE_ID,)
    assert not stale_workspace.exists()
    assert app.state.interrupted_executions == ()
    yield AsgiClient(app)


def test_create_task_returns_created_manifest_and_removes_ingress(
    client: AsgiClient, tmp_path: Path
) -> None:
    payload = _write_xls(tmp_path / "synthetic.xls")

    response = client.post(
        "/api/tasks",
        files={"primary_report": ("synthetic.xls", payload, "application/vnd.ms-excel")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "CREATED"
    assert len(body["source_files"]) == 1
    assert body["source_files"][0]["role"] == "PRIMARY_REPORT"
    assert not list((tmp_path / "storage").glob("*/ingress/*"))


def test_create_task_binds_published_template_and_freezes_rule_snapshot(
    client: AsgiClient, tmp_path: Path
) -> None:
    template_id = client.get("/api/templates").json()["templates"][0]["id"]
    payload = _write_xls(tmp_path / "bound.xls")

    response = client.post_multipart(
        "/api/tasks",
        [
            ("template_id", None, template_id, None),
            ("primary_report", "bound.xls", payload, "application/vnd.ms-excel"),
            ("supporting_manifest", None, "[]", None),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["template_id"] == template_id
    assert body["template_name"] == "硬件测试过程检查单"
    assert body["template_version"] == "A11"
    assert body["template_rule_count"] == 21
    stored = client.app.state.repositories.tasks.get(__import__("uuid").UUID(body["id"]))
    snapshot = json.loads(stored.template_rules_snapshot)
    assert len(snapshot) == 22
    assert sum(item["enabled"] for item in snapshot) == 21


def test_create_task_rejects_an_unknown_template_version(
    client: AsgiClient, tmp_path: Path
) -> None:
    payload = _write_xls(tmp_path / "unknown-template.xls")
    response = client.post_multipart(
        "/api/tasks",
        [
            ("template_id", None, "00000000-0000-0000-0000-000000000001", None),
            ("primary_report", "unknown-template.xls", payload, "application/vnd.ms-excel"),
            ("supporting_manifest", None, "[]", None),
        ],
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


def test_task_executes_the_frozen_enabled_rule_set_after_template_retirement(
    client: AsgiClient, tmp_path: Path
) -> None:
    service = client.app.state.template_service
    source = _write_a12_template(tmp_path / "A12.xls")
    template = service.upload(
        source,
        original_name="A12.xls",
        name="硬件测试过程检查单",
        version="A12",
        actor="模板管理员",
    )
    service.update_rule(
        template.id, "TR-01", {"summary": "A12 人工复核规则"}, actor="模板管理员"
    )
    service.update_rule(template.id, "TR-02", {"enabled": False}, actor="模板管理员")
    service.publish(template.id, actor="模板管理员")

    report = _write_xls(tmp_path / "dynamic.xls")
    created = client.post_multipart(
        "/api/tasks",
        [
            ("template_id", None, str(template.id), None),
            ("primary_report", "dynamic.xls", report, "application/vnd.ms-excel"),
            ("supporting_manifest", None, "[]", None),
        ],
    ).json()
    service.retire(template.id, actor="模板管理员")

    executed = client.post(f"/api/tasks/{created['id']}/execute")
    assert executed.status_code == 202
    detail = client.get(f"/api/tasks/{created['id']}").json()
    assert detail["state"] == "READY_FOR_REVIEW"
    assert detail["template_version"] == "A12"
    assert detail["template_rule_count"] == 20
    assert len(detail["rule_results"]) == 20
    by_rule = {item["rule_id"]: item for item in detail["rule_results"]}
    assert "TR-02" not in by_rule
    assert by_rule["TR-01"]["initial_status"] == "NEEDS_REVIEW"
    assert by_rule["TR-01"]["basis_code"] == "TEMPLATE_RULE_REQUIRES_MANUAL_REVIEW"
    for result in detail["rule_results"]:
        if result["initial_status"] == "NEEDS_REVIEW":
            decided = client.put(
                f"/api/tasks/{created['id']}/rules/{result['rule_id']}/manual-decision",
                json={
                    "final_status": "COMPLIANT",
                    "reason": "人工核对冻结模板要求后确认符合",
                    "supplemental_evidence": [],
                },
            )
            assert decided.status_code == 200
    completed = client.post(f"/api/tasks/{created['id']}/complete")
    assert completed.status_code == 200

    exported = client.get(f"/api/tasks/{created['id']}/export")
    assert exported.status_code == 200
    sheet = xlrd.open_workbook(file_contents=exported.content).sheet_by_name("硬件测试过程检查表")
    assert sheet.cell_value(1, 0) == "A12"
    assert sheet.cell_value(9, 3) == "√"


def test_api_routes_win_over_same_origin_static_mount(client: AsgiClient) -> None:
    response = client.get("/api/tasks/not-a-uuid")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVALID_TASK_ID"


def test_default_application_registers_docx_parser(client: AsgiClient) -> None:
    parser = client.app.state.lifecycle._evaluator._registry.for_format("DOCX")

    assert parser.format == "DOCX"


@pytest.mark.parametrize(
    ("parts", "code"),
    [
        (
            [
                ("primary_report", "synthetic.xls", b"not an xls", "application/vnd.ms-excel"),
                ("supporting_manifest", None, "{", None),
            ],
            "INVALID_UPLOAD",
        ),
        (
            [("primary_report", "synthetic.xls", b"not an xls", "application/vnd.ms-excel")],
            "INVALID_UPLOAD",
        ),
    ],
)
def test_invalid_multipart_inputs_are_stable_client_errors(client: AsgiClient, parts, code: str) -> None:
    response = client.post_multipart("/api/tasks", parts)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_create_rejects_more_than_one_primary_report(client: AsgiClient, tmp_path: Path) -> None:
    payload = _write_xls(tmp_path / "primary.xls")
    response = client.post_multipart(
        "/api/tasks",
        [
            ("primary_report", "one.xls", payload, "application/vnd.ms-excel"),
            ("primary_report", "two.xls", payload, "application/vnd.ms-excel"),
        ],
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_list_exposes_durable_source_manifests(client: AsgiClient, tmp_path: Path) -> None:
    payload = _write_xls(tmp_path / "list.xls")
    created = client.post("/api/tasks", files={"primary_report": ("list.xls", payload, "application/vnd.ms-excel")})
    assert created.status_code == 201

    listed = client.get("/api/tasks")

    assert listed.status_code == 200
    assert listed.json()["tasks"][0]["source_files"][0]["original_name"] == "list.xls"


def test_execute_is_idempotent_and_commits_exactly_one_active_result_set(client: AsgiClient, tmp_path: Path) -> None:
    payload = _write_xls(tmp_path / "execute.xls")
    created = client.post("/api/tasks", files={"primary_report": ("execute.xls", payload, "application/vnd.ms-excel")}).json()

    first = client.post(f"/api/tasks/{created['id']}/execute")
    second = client.post(f"/api/tasks/{created['id']}/execute")
    detail = client.get(f"/api/tasks/{created['id']}").json()

    assert first.status_code == second.status_code == 202
    assert detail["state"] == "READY_FOR_REVIEW"
    assert len(detail["rule_results"]) == 21
    assert "TR-05" not in {item["rule_id"] for item in detail["rule_results"]}
    assert len({item["id"] for item in detail["rule_results"]}) == 21


def test_execute_pdf_uses_the_verified_pdf_adapter(client: AsgiClient, tmp_path: Path) -> None:
    payload = _write_pdf(tmp_path / "report.pdf")
    created = client.post(
        "/api/tasks",
        files={"primary_report": ("report.pdf", payload, "application/pdf")},
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/execute")
    detail = client.get(f"/api/tasks/{created['id']}").json()

    assert response.status_code == 202
    assert detail["state"] == "READY_FOR_REVIEW"
    assert len(detail["rule_results"]) == 21
    assert detail["source_files"][0]["detected_format"] == "PDF"
    assert detail["stage_failures"] == []


def test_execute_xlsx_uses_the_registered_read_only_adapter(client: AsgiClient, tmp_path: Path) -> None:
    payload = _write_xlsx(tmp_path / "report.xlsx")
    created = client.post(
        "/api/tasks",
        files={
            "primary_report": (
                "report.xlsx",
                payload,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/execute")
    detail = client.get(f"/api/tasks/{created['id']}").json()

    assert response.status_code == 202
    assert detail["state"] == "READY_FOR_REVIEW"
    assert len(detail["rule_results"]) == 21
    assert detail["source_files"][0]["detected_format"] == "XLSX"
    assert detail["stage_failures"] == []


def test_supporting_parse_failure_names_the_actual_source_file(
    client: AsgiClient, tmp_path: Path
) -> None:
    primary = _write_xls(tmp_path / "primary.xls")
    created = client.post_multipart(
        "/api/tasks",
        [
            ("primary_report", "primary.xls", primary, "application/vnd.ms-excel"),
            ("supporting_files", "unreadable-evidence.pdf", b"%PDF-1.7\ncorrupt", "application/pdf"),
            ("supporting_manifest", None, '[{"evidence_kinds":["OTHER"]}]', None),
        ],
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/execute")
    detail = client.get(f"/api/tasks/{created['id']}").json()

    assert response.status_code == 202
    assert detail["state"] == "FAILED"
    assert detail["stage_failures"][0]["code"] == "PDF_CORRUPT"
    assert detail["stage_failures"][0]["message"].startswith("unreadable-evidence.pdf: ")


def test_supporting_manifest_is_aligned_and_persisted(client: AsgiClient, tmp_path: Path) -> None:
    primary = _write_xls(tmp_path / "primary.xls")
    supporting = _write_xls(tmp_path / "support.xls")
    response = client.post_multipart(
        "/api/tasks",
        [
            ("primary_report", "primary.xls", primary, "application/vnd.ms-excel"),
            ("supporting_files", "support.xls", supporting, "application/vnd.ms-excel"),
            ("supporting_manifest", None, '[{"evidence_kinds":["JIRA_RECORD"]}]', None),
        ],
    )

    assert response.status_code == 201
    sources = response.json()["source_files"]
    assert [(item["role"], item["evidence_kinds"]) for item in sources] == [
        ("PRIMARY_REPORT", []), ("SUPPORTING_EVIDENCE", ["JIRA_RECORD"])
    ]


def test_durable_execute_claim_has_exactly_one_concurrent_owner(client: AsgiClient, tmp_path: Path) -> None:
    payload = _write_xls(tmp_path / "claim.xls")
    task_id = client.post("/api/tasks", files={"primary_report": ("claim.xls", payload, "application/vnd.ms-excel")}).json()["id"]
    service = client.app.state.lifecycle
    from uuid import UUID

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _ignored: service.request_execution(UUID(task_id)), range(2)))

    assert sum(owner for _task, owner in outcomes) == 1
    assert client.get(f"/api/tasks/{task_id}").json()["state"] == "FILES_STAGED"


def test_concurrent_http_execute_starts_exactly_one_evaluation(client: AsgiClient, tmp_path: Path, monkeypatch) -> None:
    task_id = client.post(
        "/api/tasks",
        files={"primary_report": ("http-race.xls", _write_xls(tmp_path / "http-race.xls"), "application/vnd.ms-excel")},
    ).json()["id"]
    service = client.app.state.lifecycle
    original = service._evaluator.evaluate
    calls, lock, barrier = [], Lock(), Barrier(2)

    def counted(*args, **kwargs):
        with lock:
            calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(service._evaluator, "evaluate", counted)

    def execute_request(_unused):
        barrier.wait()
        return client.post(f"/api/tasks/{task_id}/execute")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(execute_request, range(2)))

    assert [response.status_code for response in responses] == [202, 202]
    assert calls == [1]
    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["state"] == "READY_FOR_REVIEW" and len(detail["rule_results"]) == 21


def _complete_task(client: AsgiClient, task_id: str) -> None:
    detail = client.get(f"/api/tasks/{task_id}").json()
    for result in detail["rule_results"]:
        if result["initial_status"] == "NEEDS_REVIEW":
            response = client.put(
                f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision",
                json={
                    "final_status": "COMPLIANT",
                    "reason": "人工已核对该待确认项",
                },
            )
            assert response.status_code == 200
    override = client.put(
        f"/api/tasks/{task_id}/rules/TR-01/manual-decision",
        json={
            "final_status": "NON_COMPLIANT",
            "reason": "人工确认JIRA链接与报告项目不一致",
        },
    )
    assert override.status_code == 200
    completed = client.post(f"/api/tasks/{task_id}/complete")
    assert completed.status_code == 200


def test_export_rejects_a_task_that_is_not_completed(
    client: AsgiClient, tmp_path: Path
) -> None:
    payload = _write_xls(tmp_path / "not-completed.xls")
    task_id = client.post(
        "/api/tasks",
        files={
            "primary_report": (
                "not-completed.xls",
                payload,
                "application/vnd.ms-excel",
            )
        },
    ).json()["id"]
    client.post(f"/api/tasks/{task_id}/execute")

    response = client.get(f"/api/tasks/{task_id}/export")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TASK_STATE"


def test_export_returns_a_filled_a11_copy_from_the_completed_revision(
    client: AsgiClient, tmp_path: Path
) -> None:
    payload = _write_xls(tmp_path / "completed.xls")
    task_id = client.post(
        "/api/tasks",
        files={
            "primary_report": (
                "completed.xls",
                payload,
                "application/vnd.ms-excel",
            )
        },
    ).json()["id"]
    client.post(f"/api/tasks/{task_id}/execute")
    _complete_task(client, task_id)

    response = client.get(f"/api/tasks/{task_id}/export")

    assert response.status_code == 200, response.content
    assert response.headers["content-type"].startswith("application/vnd.ms-excel")
    assert "attachment" in response.headers["content-disposition"]
    assert "completed_A11_R1.xls" in response.headers["content-disposition"]
    workbook = xlrd.open_workbook(file_contents=response.content, formatting_info=True)
    sheet = workbook.sheet_by_name("硬件测试过程检查表")
    assert sheet.row_values(9, 3, 6) == ["", "╳", ""]
    assert "人工修改原因：人工确认JIRA链接与报告项目不一致" in sheet.cell_value(9, 6)
