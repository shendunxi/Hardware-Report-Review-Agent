"""Settings defaults plus explicit ``HW_REVIEW_*`` environment overrides.

``migrations/env.py`` already reads ``HW_REVIEW_DATABASE_URL``; ``get_settings``
reads the same variable so the migration target and the runtime target cannot
diverge. Field defaults stay unchanged so explicit ``Settings(...)``
construction (used by the test suite) keeps working.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


_ENV_PREFIX = "HW_REVIEW_"

_DEFAULT_DATABASE_URL = "sqlite:///./hw-review.db"
_DEFAULT_STORAGE_ROOT = Path("./storage")
_DEFAULT_AUTH_MODE = "local"
_DEFAULT_LOCAL_SESSION_SECRET = "local-development-only-change-me"
_DEFAULT_LOCAL_SESSION_TTL_SECONDS = 28_800
_DEFAULT_LOCAL_SESSION_COOKIE = "hw_review_session"
# Must exceed the longest single evaluation, which is bounded by the DOC
# conversion timeout (DocParser defaults to 1200s); 1800s leaves 50% margin.
_DEFAULT_EXECUTION_LEASE_SECONDS = 1_800
# Parsing finishes before manual review, so a task workspace is only needed for
# a short window; 24h safely covers any in-flight execution.
_DEFAULT_WORKSPACE_TTL_SECONDS = 86_400
# Converter trust policy for .doc/.docx. "microsoft_only" is acceptance-grade;
# "any_word_compatible" admits a WPS-class host and is a development channel
# only. WordWorker validates the value, so a bad override fails startup.
_DEFAULT_WORD_AUTOMATION_POLICY = "microsoft_only"


def _default_a11_template_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "a11"
        / "hardware-test-process-checklist-a11.xls"
    )


@dataclass(frozen=True, slots=True)
class Settings:
    """Service settings; production persistence remains intentionally undecided."""

    database_url: str = _DEFAULT_DATABASE_URL
    storage_root: Path = _DEFAULT_STORAGE_ROOT
    a11_template_path: Path = field(default_factory=_default_a11_template_path)
    auth_mode: str = _DEFAULT_AUTH_MODE
    local_session_secret: str = _DEFAULT_LOCAL_SESSION_SECRET
    local_session_ttl_seconds: int = _DEFAULT_LOCAL_SESSION_TTL_SECONDS
    local_session_cookie: str = _DEFAULT_LOCAL_SESSION_COOKIE
    execution_lease_seconds: int = _DEFAULT_EXECUTION_LEASE_SECONDS
    workspace_ttl_seconds: int = _DEFAULT_WORKSPACE_TTL_SECONDS
    word_automation_policy: str = _DEFAULT_WORD_AUTOMATION_POLICY


def _text(name: str, default: str) -> str:
    value = os.environ.get(_ENV_PREFIX + name)
    return default if value is None else value


def _positive_int(name: str, default: int) -> int:
    """Parse an override strictly; a bad value must fail startup, not degrade."""

    raw = os.environ.get(_ENV_PREFIX + name)
    if raw is None:
        return default
    try:
        parsed = int(raw.strip())
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{_ENV_PREFIX}{name} must be a positive integer"
        ) from error
    if parsed <= 0:
        raise ValueError(f"{_ENV_PREFIX}{name} must be a positive integer")
    return parsed


def _path(name: str, default: Path) -> Path:
    raw = os.environ.get(_ENV_PREFIX + name)
    if raw is None or not raw.strip():
        return default
    return Path(raw.strip())


def get_settings() -> Settings:
    """Build settings from ``HW_REVIEW_*`` environment variables."""

    secret = _text("LOCAL_SESSION_SECRET", _DEFAULT_LOCAL_SESSION_SECRET)
    if not secret.strip():
        raise ValueError(f"{_ENV_PREFIX}LOCAL_SESSION_SECRET must not be blank")
    return Settings(
        database_url=_text("DATABASE_URL", _DEFAULT_DATABASE_URL),
        storage_root=_path("STORAGE_ROOT", _DEFAULT_STORAGE_ROOT),
        a11_template_path=_path("A11_TEMPLATE_PATH", _default_a11_template_path()),
        auth_mode=_text("AUTH_MODE", _DEFAULT_AUTH_MODE),
        local_session_secret=secret,
        local_session_ttl_seconds=_positive_int(
            "LOCAL_SESSION_TTL_SECONDS", _DEFAULT_LOCAL_SESSION_TTL_SECONDS
        ),
        local_session_cookie=_text("LOCAL_SESSION_COOKIE", _DEFAULT_LOCAL_SESSION_COOKIE),
        execution_lease_seconds=_positive_int(
            "EXECUTION_LEASE_SECONDS", _DEFAULT_EXECUTION_LEASE_SECONDS
        ),
        workspace_ttl_seconds=_positive_int(
            "WORKSPACE_TTL_SECONDS", _DEFAULT_WORKSPACE_TTL_SECONDS
        ),
        word_automation_policy=_text(
            "WORD_AUTOMATION_POLICY", _DEFAULT_WORD_AUTOMATION_POLICY
        ).strip(),
    )
