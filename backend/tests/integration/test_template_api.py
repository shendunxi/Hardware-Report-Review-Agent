from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
import xlrd
from alembic import command
from alembic.config import Config
from xlutils.copy import copy as copy_workbook

from hw_review.api.app import create_app
from hw_review.config import Settings


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PACKAGED_A11 = BACKEND_ROOT / "resources" / "a11" / "hardware-test-process-checklist-a11.xls"


class Response:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body

    def json(self):
        return json.loads(self._body)


class AsgiClient:
    def __init__(self, app) -> None:
        self.app = app

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: Mapping[str, str] = {},
    ) -> Response:
        async def call():
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
                    "headers": [
                        (key.lower().encode(), value.encode())
                        for key, value in headers.items()
                    ],
                    "client": ("127.0.0.1", 123),
                    "server": ("test", 80),
                },
                receive,
                send,
            )
            start = next(item for item in messages if item["type"] == "http.response.start")
            response_body = b"".join(
                item.get("body", b"")
                for item in messages
                if item["type"] == "http.response.body"
            )
            return Response(start["status"], response_body)

        return asyncio.run(call())

    def get(self, path: str) -> Response:
        return self.request("GET", path)

    def post(self, path: str, payload: dict | None = None) -> Response:
        if payload is None:
            return self.request("POST", path)
        return self.request(
            "POST",
            path,
            body=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"content-type": "application/json"},
        )

    def put(self, path: str, payload: dict) -> Response:
        return self.request(
            "PUT",
            path,
            body=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"content-type": "application/json"},
        )

    def delete(self, path: str) -> Response:
        return self.request("DELETE", path)

    def upload_template(
        self,
        payload: bytes,
        *,
        filename: str,
        name: str,
        version: str,
        actor: str = "模板管理员",
    ) -> Response:
        boundary = "template-api-boundary"
        parts = [
            ("source", filename, payload, "application/vnd.ms-excel"),
            ("name", None, name, None),
            ("version", None, version, None),
            ("actor", None, actor, None),
        ]
        body = bytearray()
        for field, part_filename, value, content_type in parts:
            body.extend(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"'.encode()
            )
            if part_filename is not None:
                body.extend(
                    f'; filename="{part_filename}"\r\nContent-Type: {content_type}'.encode()
                )
            body.extend(b"\r\n\r\n")
            body.extend(value if isinstance(value, bytes) else value.encode("utf-8"))
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return self.request(
            "POST",
            "/api/templates",
            body=bytes(body),
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        )


def _migrate(database: Path) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")


def _a12_bytes(path: Path) -> bytes:
    source = xlrd.open_workbook(PACKAGED_A11, formatting_info=True)
    writable = copy_workbook(source)
    writable.get_sheet(source.sheet_names().index("硬件测试过程检查表")).write(1, 0, "A12")
    writable.save(str(path))
    return path.read_bytes()


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    database = tmp_path / "review.db"
    _migrate(database)
    return Settings(
        database_url=f"sqlite:///{database.as_posix()}",
        storage_root=tmp_path / "storage",
        a11_template_path=PACKAGED_A11,
        auth_mode="disabled",
    )


def test_template_api_upload_edit_publish_retire_and_restart(
    app_settings: Settings, tmp_path: Path
) -> None:
    first_app = create_app(app_settings)
    client = AsgiClient(first_app)
    baseline = client.get("/api/templates")
    assert baseline.status_code == 200
    assert [(item["version"], item["status"]) for item in baseline.json()["templates"]] == [
        ("A11", "PUBLISHED")
    ]

    uploaded = client.upload_template(
        _a12_bytes(tmp_path / "A12.xls"),
        filename="硬件测试过程检查单-A12.xls",
        name="硬件测试过程检查单",
        version="A12",
    )
    assert uploaded.status_code == 201
    template_id = uploaded.json()["id"]
    detail = client.get(f"/api/templates/{template_id}")
    assert detail.status_code == 200
    assert len(detail.json()["rules"]) == 22

    changed = client.put(
        f"/api/templates/{template_id}/rules/TR-01",
        {"summary": "JIRA 项目与链接检查", "enabled": False, "main_judgment": "DISABLED"},
    )
    assert changed.status_code == 200
    assert changed.json()["summary"] == "JIRA 项目与链接检查"

    added = client.post(
        f"/api/templates/{template_id}/rules",
        {
            "rule_id": "CUSTOM-01",
            "summary": "新增人工检查项",
            "verifiable_requirement": "由审核人员核对新增要求",
            "required_materials": "新增要求证明材料",
            "main_judgment": "MANUAL",
            "confirmed_boundary": "未配置自动判定条件时进入待人工确认",
            "enabled": True,
        },
    )
    assert added.status_code == 201
    assert client.delete(f"/api/templates/{template_id}/rules/CUSTOM-01").status_code == 204

    published = client.post(f"/api/templates/{template_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"
    immutable = client.put(
        f"/api/templates/{template_id}/rules/TR-01", {"summary": "不得修改"}
    )
    assert immutable.status_code == 409
    assert immutable.json()["error"]["code"] == "TEMPLATE_IMMUTABLE"
    retired = client.post(f"/api/templates/{template_id}/retire")
    assert retired.status_code == 200
    assert retired.json()["status"] == "RETIRED"

    first_app.state.repositories.close()
    restarted = AsgiClient(create_app(app_settings))
    restored = restarted.get(f"/api/templates/{template_id}")
    assert restored.status_code == 200
    assert restored.json()["template"]["status"] == "RETIRED"
    assert len(restored.json()["rules"]) == 22
    restarted.app.state.repositories.close()


def test_template_api_returns_stable_upload_and_not_found_errors(
    app_settings: Settings,
) -> None:
    client = AsgiClient(create_app(app_settings))
    unsupported = client.upload_template(
        b"not xls",
        filename="template.xlsx",
        name="硬件测试过程检查单",
        version="A12",
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["error"]["code"] == "TEMPLATE_FORMAT_UNSUPPORTED"

    missing = client.get("/api/templates/00000000-0000-0000-0000-000000000001")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"
    client.app.state.repositories.close()
