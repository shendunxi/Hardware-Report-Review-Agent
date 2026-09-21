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
# Semantic rule judgement via an authorized LLM. Disabled by default so that an
# unconfigured deployment sends nothing off the machine, matching the PRD rule
# that report content must never leave without explicit authorization.
_DEFAULT_LLM_ENABLED = False
_DEFAULT_LLM_BASE_URL = ""
_DEFAULT_LLM_API_KEY = ""
_DEFAULT_LLM_MODEL = ""
_DEFAULT_LLM_TIMEOUT_SECONDS = 180
# The provider is a reasoning model: a small budget is consumed entirely by the
# chain of thought and `content` comes back empty (reproduced 2026-09-20).
_DEFAULT_LLM_MAX_TOKENS = 4096
# The largest frozen sample normalizes to ~83k characters, so this is a guard
# against pathological inputs rather than a routine limit. Exceeding it degrades
# the semantic rules; the evidence is never truncated.
_DEFAULT_LLM_MAX_EVIDENCE_LINES = 12_000
# "all" sends every enabled check item to the model; "semantic_only" keeps the
# model as a fallback for rules the deterministic engine left undecided.
LLM_SCOPES = ("all", "semantic_only")
_DEFAULT_LLM_SCOPE = "all"
# A production deployment must not be able to look like a developer machine.
# "development" keeps the relative-path defaults usable; "production" refuses
# every setting that only makes sense inside a checkout.
ENVIRONMENTS = ("development", "production")
_DEFAULT_ENVIRONMENT = "development"
# Only these modes exist until a real identity provider is wired up. Anything
# else must stop startup rather than be treated as "no authentication".
AUTH_MODES = ("local", "disabled")
# The documented default plus the usual placeholders. Accepting any of these as
# the session secret would let anyone who read the README forge a signed session.
_WEAK_SESSION_SECRETS = frozenset(
    {
        _DEFAULT_LOCAL_SESSION_SECRET,
        "change-me",
        "changeme",
        "password",
        "secret",
        "test",
    }
)
_MINIMUM_SESSION_SECRET_LENGTH = 32


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
    llm_enabled: bool = _DEFAULT_LLM_ENABLED
    llm_base_url: str = _DEFAULT_LLM_BASE_URL
    llm_api_key: str = _DEFAULT_LLM_API_KEY
    llm_model: str = _DEFAULT_LLM_MODEL
    llm_timeout_seconds: int = _DEFAULT_LLM_TIMEOUT_SECONDS
    llm_max_tokens: int = _DEFAULT_LLM_MAX_TOKENS
    llm_max_evidence_lines: int = _DEFAULT_LLM_MAX_EVIDENCE_LINES
    llm_scope: str = _DEFAULT_LLM_SCOPE
    environment: str = _DEFAULT_ENVIRONMENT


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


def _is_relative_database_url(url: str) -> bool:
    """True when a SQLite URL resolves against the process working directory.

    ``sqlite:///./x`` and ``sqlite:///x`` are relative; ``sqlite:////x`` (the
    extra slash is the root) and ``sqlite:///C:/x`` are absolute. A server-based
    URL never depends on the working directory, so it is never flagged.
    """

    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return False
    remainder = url[len(prefix) :]
    if not remainder:
        return False
    if remainder.startswith(("/", "\\")):
        return False
    return not Path(remainder).is_absolute()


def self_check(settings: Settings) -> tuple[str, ...]:
    """Validate a built ``Settings``; warnings are returned, blockers are raised.

    Anything that makes a deployment unsafe or ambiguous stops startup instead of
    degrading: an unknown auth mode, a shipped-default session secret, or -- in
    production -- a data location that depends on the process working directory.
    """

    if settings.auth_mode not in AUTH_MODES:
        raise ValueError(
            f"{_ENV_PREFIX}AUTH_MODE must be one of: {', '.join(AUTH_MODES)}; "
            "no external identity provider is implemented yet"
        )

    relative = [
        name
        for name, is_relative in (
            ("DATABASE_URL", _is_relative_database_url(settings.database_url)),
            ("STORAGE_ROOT", not Path(settings.storage_root).is_absolute()),
        )
        if is_relative
    ]
    warnings: list[str] = []
    if relative:
        # The defaults are relative on purpose so that uvicorn started from
        # backend/ just works. Outside a checkout that is an accident waiting to
        # happen, which is why production refuses it outright.
        detail = f"{', '.join(relative)} resolve against the process working directory"
        if settings.environment == "production":
            raise ValueError(
                f"production requires absolute paths: {detail}; "
                f"set {_ENV_PREFIX}ENVIRONMENT=development for a local run"
            )
        warnings.append(
            f"{detail} (allowed because {_ENV_PREFIX}ENVIRONMENT="
            f"{settings.environment})"
        )

    if settings.local_session_secret in _WEAK_SESSION_SECRETS or (
        len(settings.local_session_secret) < _MINIMUM_SESSION_SECRET_LENGTH
    ):
        detail = (
            f"{_ENV_PREFIX}LOCAL_SESSION_SECRET is a shipped default or shorter "
            f"than {_MINIMUM_SESSION_SECRET_LENGTH} characters"
        )
        if settings.environment == "production":
            raise ValueError(f"production requires a strong session secret: {detail}")
        warnings.append(f"{detail} (allowed because {_ENV_PREFIX}ENVIRONMENT="
                        f"{settings.environment})")

    if settings.environment == "production" and settings.auth_mode == "disabled":
        raise ValueError(
            "production must not run with "
            f"{_ENV_PREFIX}AUTH_MODE=disabled; that mode exists for tests"
        )

    if not settings.llm_enabled:
        warnings.append(
            "semantic judgement is disabled; semantic rules will stop at "
            "NEEDS_REVIEW and no report content leaves this machine"
        )
    return tuple(warnings)


def _flag(name: str, default: bool) -> bool:
    """Parse a boolean override strictly; a bad value must fail startup."""

    raw = os.environ.get(_ENV_PREFIX + name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{_ENV_PREFIX}{name} must be a boolean")


def get_settings() -> Settings:
    """Build settings from ``HW_REVIEW_*`` environment variables."""

    secret = _text("LOCAL_SESSION_SECRET", _DEFAULT_LOCAL_SESSION_SECRET)
    if not secret.strip():
        raise ValueError(f"{_ENV_PREFIX}LOCAL_SESSION_SECRET must not be blank")
    llm_enabled = _flag("LLM_ENABLED", _DEFAULT_LLM_ENABLED)
    llm_base_url = _text("LLM_BASE_URL", _DEFAULT_LLM_BASE_URL).strip()
    llm_api_key = _text("LLM_API_KEY", _DEFAULT_LLM_API_KEY).strip()
    llm_model = _text("LLM_MODEL", _DEFAULT_LLM_MODEL).strip()
    environment = _text("ENVIRONMENT", _DEFAULT_ENVIRONMENT).strip().casefold()
    if environment not in ENVIRONMENTS:
        raise ValueError(
            f"{_ENV_PREFIX}ENVIRONMENT must be one of: {', '.join(ENVIRONMENTS)}"
        )
    llm_scope = _text("LLM_SCOPE", _DEFAULT_LLM_SCOPE).strip()
    if llm_enabled:
        # Half-configured means the semantic rules would silently stay manual, so
        # an enabled provider missing any part of its identity must not start.
        incomplete = [
            name
            for name, value in (
                ("LLM_BASE_URL", llm_base_url),
                ("LLM_API_KEY", llm_api_key),
                ("LLM_MODEL", llm_model),
            )
            if not value
        ]
        if incomplete:
            raise ValueError(
                f"{_ENV_PREFIX}LLM_ENABLED=true requires: {', '.join(incomplete)}"
            )
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
        llm_enabled=llm_enabled,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_timeout_seconds=_positive_int(
            "LLM_TIMEOUT_SECONDS", _DEFAULT_LLM_TIMEOUT_SECONDS
        ),
        llm_max_tokens=_positive_int("LLM_MAX_TOKENS", _DEFAULT_LLM_MAX_TOKENS),
        llm_max_evidence_lines=_positive_int(
            "LLM_MAX_EVIDENCE_LINES", _DEFAULT_LLM_MAX_EVIDENCE_LINES
        ),
        llm_scope=llm_scope,
        environment=environment,
    )
