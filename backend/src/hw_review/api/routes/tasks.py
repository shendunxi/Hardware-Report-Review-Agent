"""Local-review task and completed-checklist export endpoints."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from hw_review.api.access import AccessContext, require_reviewer
from hw_review.api.errors import error_response
from hw_review.domain import EvidenceKind, FileRole, SourceFileCreate
from hw_review.services.lifecycle import LifecycleError
from hw_review.services.template_binding import enabled_rules_for_task, rules_for_task
from hw_review.services.templates import TemplateServiceError


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class ManualDecisionPayload(BaseModel):
    final_status: str
    reason: str = Field(min_length=1)
    supplemental_evidence: tuple = ()


def _payload(item):
    return item.model_dump(mode="json") if hasattr(item, "model_dump") else item


def _task_payload(service, task, sources=()):
    body = _payload(task)
    body.pop("template_source_path", None)
    body.pop("template_source_sha256", None)
    body.pop("template_rules_snapshot", None)
    try:
        body["template_rule_count"] = len(enabled_rules_for_task(task))
    except ValueError:
        body["template_rule_count"] = 0
    body["source_files"] = [_payload(source) for source in sources]
    # Derived server-side so the UI never re-implements the execution-lease rule.
    body["execution"] = service.execution_status(task)
    return body


def _revision_payload(revision):
    body = _payload(revision)
    try:
        body["snapshot"] = json.loads(revision.result_snapshot)
    except (TypeError, json.JSONDecodeError):
        body["snapshot"] = None
    return body


def _service(request: Request):
    return request.app.state.lifecycle


def _parse_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise LifecycleError("INVALID_TASK_ID", "task ID is invalid") from error


def _safe_name(name: str | None) -> str:
    if not name or not name.strip() or Path(name).name != name or name in {".", ".."}:
        raise LifecycleError("INVALID_UPLOAD", "upload filename is blank or unsafe")
    return name


@router.post("", status_code=201)
async def create_task(
    request: Request,
    _principal: Annotated[AccessContext, Depends(require_reviewer)],
    primary_report: Annotated[UploadFile, File(...)],
    supporting_files: Annotated[list[UploadFile], File()] = [],
    supporting_manifest: Annotated[str | None, Form()] = None,
    template_id: Annotated[str | None, Form()] = None,
):
    try:
        form = await request.form()
        if len(form.getlist("primary_report")) != 1:
            raise LifecycleError("INVALID_UPLOAD", "exactly one primary report is required")
        primary_name = _safe_name(primary_report.filename)
        try:
            manifests = json.loads(supporting_manifest or "[]")
        except json.JSONDecodeError as error:
            raise LifecycleError("INVALID_UPLOAD", "supporting manifest is not valid JSON") from error
        if not isinstance(manifests, list) or len(manifests) != len(supporting_files):
            raise LifecycleError("INVALID_UPLOAD", "supporting manifest must align with supporting files")
        task_id = uuid4()
        ingress = Path(request.app.state.settings.storage_root) / str(task_id) / "ingress"
        ingress.mkdir(parents=True, exist_ok=False)
        files = []
        primary_path = ingress / "primary-upload"
        primary_bytes = await primary_report.read()
        if not primary_bytes:
            raise LifecycleError("INVALID_UPLOAD", "primary report is empty")
        primary_path.write_bytes(primary_bytes)
        files.append((primary_path.with_suffix(Path(primary_name).suffix), SourceFileCreate(role=FileRole.PRIMARY_REPORT, original_name=primary_name)))
        primary_path.rename(files[-1][0])
        for index, (upload, manifest) in enumerate(zip(supporting_files, manifests, strict=True)):
            name = _safe_name(upload.filename)
            if not isinstance(manifest, dict) or not isinstance(manifest.get("evidence_kinds"), list):
                raise LifecycleError("INVALID_UPLOAD", "supporting evidence_kinds are required")
            try:
                kinds = tuple(EvidenceKind(item) for item in manifest["evidence_kinds"])
            except ValueError as error:
                raise LifecycleError("INVALID_UPLOAD", "supporting evidence kind is invalid") from error
            if not kinds:
                raise LifecycleError("INVALID_UPLOAD", "supporting evidence_kinds are required")
            path = ingress / f"support-{index}{Path(name).suffix}"
            content = await upload.read()
            if not content:
                raise LifecycleError("INVALID_UPLOAD", "supporting file is empty")
            path.write_bytes(content)
            files.append((path, SourceFileCreate(role=FileRole.SUPPORTING_EVIDENCE, original_name=name, evidence_kinds=kinds)))
        try:
            parsed_template_id = UUID(template_id) if template_id else None
        except ValueError as error:
            raise TemplateServiceError("TEMPLATE_NOT_FOUND", "模板版本不存在。") from error
        template, template_rules = request.app.state.template_service.published_binding(parsed_template_id)
        task, sources = _service(request).create(
            primary_name,
            tuple(files),
            task_id=task_id,
            template=template,
            template_rules=template_rules,
        )
        return _task_payload(_service(request), task, sources)
    finally:
        if "ingress" in locals():
            shutil.rmtree(ingress, ignore_errors=True)


@router.post("/{task_id}/execute", status_code=202)
async def execute_task(
    request: Request,
    task_id: str,
    background_tasks: BackgroundTasks,
    _principal: Annotated[AccessContext, Depends(require_reviewer)],
):
    parsed = _parse_id(task_id)
    service = _service(request)
    current, owns_execution = service.request_execution(parsed)

    def run() -> None:
        try:
            service.execute_claimed(parsed)
        except LifecycleError:
            pass

    if owns_execution:
        background_tasks.add_task(run)
    return _task_payload(service, current)


@router.get("")
async def list_tasks(
    request: Request,
    _principal: Annotated[AccessContext, Depends(require_reviewer)],
):
    service = _service(request)
    # list_summary keeps this endpoint off the repository bundle: the read order
    # for a task's children belongs next to the single-task detail it must stay
    # consistent with.
    return {
        "tasks": [
            {
                **_task_payload(service, record["task"], record["source_files"]),
                "stage_failures": [_payload(item) for item in record["stage_failures"]],
                "rule_results": [_payload(item) for item in record["rule_results"]],
                "manual_decisions": [_payload(item) for item in record["manual_decisions"]],
                "revisions": [_payload(item) for item in record["revisions"]],
            }
            for record in service.list_summary()
        ]
    }


@router.get("/{task_id}")
async def get_task(
    request: Request,
    task_id: str,
    _principal: Annotated[AccessContext, Depends(require_reviewer)],
):
    detail = _service(request).detail(_parse_id(task_id))
    return {
        **_task_payload(_service(request), detail["task"], detail["source_files"]),
        "template_rules": [_payload(item) for item in rules_for_task(detail["task"])],
        "stage_failures": [_payload(item) for item in detail["stage_failures"]],
        "rule_results": [_payload(item) for item in detail["rule_results"]],
        "manual_decisions": [_payload(item) for item in detail["manual_decisions"]],
        "revisions": [_revision_payload(item) for item in detail["revisions"]],
    }


@router.get("/{task_id}/export")
async def export_checklist(
    request: Request,
    task_id: str,
    _principal: Annotated[AccessContext, Depends(require_reviewer)],
):
    artifact = request.app.state.checklist_export.export(_parse_id(task_id))
    encoded_name = quote(artifact.filename)
    return Response(
        content=artifact.content,
        media_type="application/vnd.ms-excel",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Cache-Control": "no-store",
        },
    )


@router.put("/{task_id}/rules/{rule_id}/manual-decision")
async def save_manual_decision(
    request: Request,
    task_id: str,
    rule_id: str,
    payload: ManualDecisionPayload,
    principal: Annotated[AccessContext, Depends(require_reviewer)],
):
    decision = _service(request).save_decision(
        _parse_id(task_id),
        rule_id,
        payload.final_status,
        payload.reason,
        principal.actor,
        payload.supplemental_evidence,
    )
    return _payload(decision)


@router.post("/{task_id}/complete")
async def complete_task(
    request: Request,
    task_id: str,
    _principal: Annotated[AccessContext, Depends(require_reviewer)],
):
    task, revision = _service(request).complete(_parse_id(task_id))
    return {**_task_payload(_service(request), task), "revision": _payload(revision)}


@router.post("/{task_id}/reopen")
async def reopen_task(
    request: Request,
    task_id: str,
    _principal: Annotated[AccessContext, Depends(require_reviewer)],
):
    service = _service(request)
    return _task_payload(service, service.reopen(_parse_id(task_id)))
