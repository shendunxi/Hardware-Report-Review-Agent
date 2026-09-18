"""Loopback-only local session endpoints for the development deployment."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from hw_review.api.access import (
    AccessContext,
    AccessError,
    LocalSessionCodec,
    REVIEW_ROLE,
    TEMPLATE_ROLE,
    require_authenticated,
)


router = APIRouter(prefix="/api/session", tags=["session"])


class LocalSessionPayload(BaseModel):
    role: Literal["tester", "admin", "combined"]


_CONTEXTS = {
    "tester": AccessContext("测试报告审核", frozenset({REVIEW_ROLE}), "tester"),
    "admin": AccessContext("模板规则管理", frozenset({TEMPLATE_ROLE}), "admin"),
    "combined": AccessContext(
        "组合角色", frozenset({REVIEW_ROLE, TEMPLATE_ROLE}), "combined"
    ),
}


def _payload(context: AccessContext) -> dict[str, object]:
    return {
        "actor": context.actor,
        "roles": sorted(context.roles),
        "role": context.selected_role,
    }


@router.post("/local")
async def select_local_session(
    request: Request, response: Response, payload: LocalSessionPayload
):
    client_host = request.client.host if request.client else None
    if client_host not in {"127.0.0.1", "::1"}:
        raise AccessError("PERMISSION_DENIED", "本地角色选择只允许从回环地址访问。")
    settings = request.app.state.settings
    if settings.auth_mode != "local":
        raise AccessError("PERMISSION_DENIED", "当前环境未启用本地角色选择。")
    context = _CONTEXTS[payload.role]
    token = LocalSessionCodec(
        settings.local_session_secret, settings.local_session_ttl_seconds
    ).encode(context)
    response.set_cookie(
        key=settings.local_session_cookie,
        value=token,
        max_age=settings.local_session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/",
    )
    return _payload(context)


@router.get("")
async def current_session(
    principal: Annotated[AccessContext, Depends(require_authenticated)],
):
    return _payload(principal)
