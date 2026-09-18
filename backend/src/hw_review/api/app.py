"""FastAPI factory: API routes first, then the same-origin Vue application."""

from __future__ import annotations

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
from hw_review.services.staging import FileStager
from hw_review.services.templates import TemplateService, TemplateServiceError


class SPAStaticFiles(StaticFiles):
    """Serve built assets normally and send history-mode routes to index.html."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.auth_mode not in {"local", "disabled"}:
        raise RuntimeError("AUTH_PROVIDER_NOT_CONFIGURED")
    bundle = repositories(settings.database_url)
    lifecycle = LifecycleService(
        bundle,
        FileStager(settings.storage_root),
        EvaluationService(
            ParserRegistry(
                (
                    XlsParser(),
                    XlsxParser(),
                    DocParser(),
                    DocParser(format="DOCX"),
                    PdfParser(),
                )
            ),
            A11Engine(),
        ),
        WorkspaceCleaner(settings.storage_root),
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
