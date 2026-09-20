"""FastAPI factory: API routes first, then the same-origin Vue application."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from hw_review.api.access import AccessError
from hw_review.api.errors import access_error_handler, lifecycle_error_handler, request_validation_error_handler, template_error_handler
from fastapi.exceptions import RequestValidationError
from hw_review.api.routes.tasks import router as task_router
from hw_review.api.routes.templates import router as template_router
from hw_review.api.routes.session import router as session_router
from hw_review.config import Settings, get_settings
from hw_review.parsers import DocParser, PdfParser, XlsParser, XlsxParser
from hw_review.persistence import repositories
from hw_review.rules import A11Engine
from hw_review.services.cleanup import WorkspaceCleaner
from hw_review.services.a11_export import A11ChecklistExportService, A11ChecklistWriter
from hw_review.services.evaluation import EvaluationService
from hw_review.services.lifecycle import LifecycleError, LifecycleService
from hw_review.services.parsing import ParserRegistry
from hw_review.services.semantic_judge import OpenAiCompatSemanticJudge
from hw_review.services.staging import FileStager
from hw_review.services.templates import TemplateService, TemplateServiceError


_LOGGER = logging.getLogger("hw_review.api")


class SPAStaticFiles(StaticFiles):
    """Serve built assets normally and send history-mode routes to index.html."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)


def _sweep_expired_workspaces(cleaner: WorkspaceCleaner) -> tuple[str, ...]:
    """Reclaim orphaned task workspaces once at startup.

    A failure here must never block startup: the sweep is housekeeping, and an
    unusable workspace only wastes disk.
    """

    try:
        reclaimed = cleaner.clean_expired(datetime.now(timezone.utc))
    except Exception as error:  # noqa: BLE001 - startup must survive bad workspaces
        _LOGGER.warning("workspace expiry sweep failed: %s", error)
        return ()
    if reclaimed:
        _LOGGER.info("reclaimed %d expired task workspace(s)", len(reclaimed))
    return tuple(str(task_id) for task_id in reclaimed)


def _report_interrupted_executions(lifecycle: LifecycleService) -> tuple[dict, ...]:
    """Surface interrupted executions without mutating any task state.

    Startup deliberately does not rewrite state: a second worker may still own
    the task. An abandoned claim only becomes reclaimable once its lease expires.
    """

    try:
        interrupted = lifecycle.inspect_interrupted()
    except Exception as error:  # noqa: BLE001 - diagnostics must not block startup
        _LOGGER.warning("interrupted execution inspection failed: %s", error)
        return ()
    for item in interrupted:
        _LOGGER.warning(
            "task %s interrupted in %s; reclaimable in %.0fs",
            item["task_id"],
            item["state"],
            item["seconds_until_reclaimable"],
        )
    return tuple(interrupted)


def _semantic_judge(settings: Settings):
    """Build the semantic judge only when it is explicitly authorized.

    A disabled judge means the semantic rules keep their manual fallback and no
    report content ever leaves the machine.
    """

    if not settings.llm_enabled:
        return None
    judge = OpenAiCompatSemanticJudge(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
        max_evidence_lines=settings.llm_max_evidence_lines,
    )
    _LOGGER.warning(
        "semantic judgement ENABLED: report text will be sent to %s (model %s)",
        settings.llm_base_url,
        settings.llm_model,
    )
    return judge


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.auth_mode not in {"local", "disabled"}:
        raise RuntimeError("AUTH_PROVIDER_NOT_CONFIGURED")
    bundle = repositories(settings.database_url)
    cleaner = WorkspaceCleaner(
        settings.storage_root,
        expiry=timedelta(seconds=settings.workspace_ttl_seconds),
    )
    lifecycle = LifecycleService(
        bundle,
        FileStager(settings.storage_root),
        EvaluationService(
            ParserRegistry(
                (
                    XlsParser(),
                    XlsxParser(),
                    DocParser(word_policy=settings.word_automation_policy),
                    DocParser(
                        format="DOCX", word_policy=settings.word_automation_policy
                    ),
                    PdfParser(),
                )
            ),
            A11Engine(),
            judge=_semantic_judge(settings),
            llm_scope=settings.llm_scope,
        ),
        cleaner,
        execution_lease_seconds=settings.execution_lease_seconds,
    )
    app = FastAPI()
    app.state.settings, app.state.lifecycle, app.state.repositories = settings, lifecycle, bundle
    app.state.checklist_export = A11ChecklistExportService(
        bundle, A11ChecklistWriter(settings.a11_template_path)
    )
    app.state.template_service = TemplateService(
        bundle,
        template_root=Path(settings.storage_root) / "templates",
        baseline_path=settings.a11_template_path,
    )
    app.state.template_service.ensure_baseline()
    app.state.startup_reclamation = _sweep_expired_workspaces(cleaner)
    app.state.interrupted_executions = _report_interrupted_executions(lifecycle)
    app.add_exception_handler(LifecycleError, lifecycle_error_handler)
    app.add_exception_handler(TemplateServiceError, template_error_handler)
    app.add_exception_handler(AccessError, access_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.include_router(task_router)
    app.include_router(template_router)
    app.include_router(session_router)
    repository_root = Path(__file__).resolve().parents[4]
    vue_root = repository_root / "frontend" / "dist"
    prototype_root = repository_root / "prototype" / "a11-ui"
    static_root = vue_root if (vue_root / "index.html").is_file() else prototype_root
    if static_root.is_dir():
        app.mount("/", SPAStaticFiles(directory=static_root, html=True), name="frontend")

    @app.on_event("shutdown")
    def shutdown() -> None:
        bundle.close()

    return app
