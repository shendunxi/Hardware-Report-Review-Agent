"""Persisted template upload, validation and lifecycle endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict

from hw_review.api.access import (
    AccessContext,
    require_authenticated,
    require_template_manager,
)
from hw_review.services.templates import TemplateService, TemplateServiceError


router = APIRouter(prefix="/api/templates", tags=["templates"])


class RuleUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    verifiable_requirement: str | None = None
    required_materials: str | None = None
    main_judgment: str | None = None
    confirmed_boundary: str | None = None
    enabled: bool | None = None


class RuleCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    summary: str
    verifiable_requirement: str
    required_materials: str
    main_judgment: str
    confirmed_boundary: str
    enabled: bool


def _service(request: Request) -> TemplateService:
    return request.app.state.template_service


def _template_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise TemplateServiceError("TEMPLATE_NOT_FOUND", "模板版本不存在。") from error


def _payload(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


@router.get("")
async def list_templates(
    request: Request,
    _principal: Annotated[AccessContext, Depends(require_authenticated)],
):
    return {"templates": [_payload(item) for item in _service(request).list_versions()]}


@router.post("", status_code=201)
async def upload_template(
    request: Request,
    principal: Annotated[AccessContext, Depends(require_template_manager)],
    source: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form(...),
):
    original_name = Path(source.filename or "template.xls").name
    suffix = Path(original_name).suffix.lower()
    upload_root = Path(request.app.state.settings.storage_root) / "_template_uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    temporary = upload_root / f"{uuid4()}{suffix}"
    try:
        content = await source.read()
        if not content:
            raise TemplateServiceError("TEMPLATE_FILE_EMPTY", "上传模板不能为空。")
        temporary.write_bytes(content)
        return _payload(
            _service(request).upload(
                temporary,
                original_name=original_name,
                name=name,
                version=version,
                actor=principal.actor,
            )
        )
    finally:
        temporary.unlink(missing_ok=True)
        try:
            upload_root.rmdir()
        except OSError:
            pass


@router.get("/{template_id}")
async def get_template(
    request: Request,
    template_id: str,
    _principal: Annotated[AccessContext, Depends(require_authenticated)],
):
    detail = _service(request).detail(_template_id(template_id))
    return {
        "template": _payload(detail["template"]),
        "rules": [_payload(item) for item in detail["rules"]],
    }


@router.put("/{template_id}/rules/{rule_id}")
async def update_template_rule(
    request: Request,
    template_id: str,
    rule_id: str,
    payload: RuleUpdatePayload,
    _principal: Annotated[AccessContext, Depends(require_template_manager)],
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise TemplateServiceError(
            "TEMPLATE_RULE_UPDATE_INVALID", "至少提供一个需要修改的字段。"
        )
    return _payload(
        _service(request).update_rule(_template_id(template_id), rule_id, changes)
    )


@router.post("/{template_id}/rules", status_code=201)
async def add_template_rule(
    request: Request,
    template_id: str,
    payload: RuleCreatePayload,
    _principal: Annotated[AccessContext, Depends(require_template_manager)],
):
    return _payload(
        _service(request).add_rule(
            _template_id(template_id), payload.model_dump()
        )
    )


@router.delete("/{template_id}/rules/{rule_id}", status_code=204)
async def delete_template_rule(
    request: Request,
    template_id: str,
    rule_id: str,
    _principal: Annotated[AccessContext, Depends(require_template_manager)],
):
    _service(request).delete_rule(_template_id(template_id), rule_id)
    return Response(status_code=204)


@router.post("/{template_id}/publish")
async def publish_template(
    request: Request,
    template_id: str,
    _principal: Annotated[AccessContext, Depends(require_template_manager)],
):
    return _payload(_service(request).publish(_template_id(template_id)))


@router.post("/{template_id}/retire")
async def retire_template(
    request: Request,
    template_id: str,
    _principal: Annotated[AccessContext, Depends(require_template_manager)],
):
    return _payload(_service(request).retire(_template_id(template_id)))
