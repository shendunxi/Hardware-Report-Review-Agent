"""Server-owned access contexts and signed loopback development sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request


REVIEW_ROLE = "review"
TEMPLATE_ROLE = "template"


class AccessError(Exception):
    """Stable authentication or authorization failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AccessContext:
    actor: str
    roles: frozenset[str]
    selected_role: str


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class LocalSessionCodec:
    """HMAC-sign a compact local-session payload without external dependencies."""

    def __init__(self, secret: str, ttl_seconds: int) -> None:
        if not secret:
            raise ValueError("local session secret is required")
        if ttl_seconds <= 0:
            raise ValueError("local session TTL must be positive")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def encode(self, context: AccessContext, *, now: int | None = None) -> str:
        issued_at = int(time.time() if now is None else now)
        payload = json.dumps(
            {
                "actor": context.actor,
                "roles": sorted(context.roles),
                "role": context.selected_role,
                "issued_at": issued_at,
                "expires_at": issued_at + self._ttl_seconds,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"{_encode(payload)}.{_encode(signature)}"

    def decode(self, token: str, *, now: int | None = None) -> AccessContext:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            payload = _decode(encoded_payload)
            signature = _decode(encoded_signature)
            expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature mismatch")
            values = json.loads(payload)
            actor = values["actor"]
            roles = values["roles"]
            selected_role = values["role"]
            issued_at = values["issued_at"]
            expires_at = values["expires_at"]
            current = int(time.time() if now is None else now)
            if not isinstance(actor, str) or not actor.strip():
                raise ValueError("actor is invalid")
            if not isinstance(roles, list) or not roles:
                raise ValueError("roles are invalid")
            normalized_roles = frozenset(roles)
            if not normalized_roles <= {REVIEW_ROLE, TEMPLATE_ROLE}:
                raise ValueError("roles are invalid")
            if selected_role not in {"tester", "admin", "combined"}:
                raise ValueError("selected role is invalid")
            if not isinstance(issued_at, int) or not isinstance(expires_at, int):
                raise ValueError("timestamps are invalid")
            if expires_at <= current or expires_at - issued_at != self._ttl_seconds:
                raise ValueError("session is expired or invalid")
            return AccessContext(actor.strip(), normalized_roles, selected_role)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise AccessError(
                "AUTHENTICATION_REQUIRED", "本地会话未建立、已失效或签名无效。"
            ) from error


def require_authenticated(request: Request) -> AccessContext:
    settings = request.app.state.settings
    if settings.auth_mode == "disabled":
        return AccessContext(
            actor="local-review",
            roles=frozenset({REVIEW_ROLE, TEMPLATE_ROLE}),
            selected_role="combined",
        )
    token = request.cookies.get(settings.local_session_cookie)
    if not token:
        raise AccessError("AUTHENTICATION_REQUIRED", "请先建立本地会话。")
    return LocalSessionCodec(
        settings.local_session_secret, settings.local_session_ttl_seconds
    ).decode(token)


def require_reviewer(
    principal: Annotated[AccessContext, Depends(require_authenticated)],
) -> AccessContext:
    if REVIEW_ROLE not in principal.roles:
        raise AccessError("PERMISSION_DENIED", "当前账号没有测试报告审核权限。")
    return principal


def require_template_manager(
    principal: Annotated[AccessContext, Depends(require_authenticated)],
) -> AccessContext:
    if TEMPLATE_ROLE not in principal.roles:
        raise AccessError("PERMISSION_DENIED", "当前账号没有模板规则管理权限。")
    return principal
