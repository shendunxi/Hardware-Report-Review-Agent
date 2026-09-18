"""Frozen public error envelope and application-error mapping."""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from hw_review.services.lifecycle import LifecycleError
from hw_review.services.templates import TemplateServiceError
from hw_review.api.access import AccessError


_STATUS = {
    "TASK_NOT_FOUND": 404, "INVALID_TASK_ID": 404, "INVALID_RULE": 422,
    "INVALID_UPLOAD": 422, "INVALID_STATUS": 422, "INVALID_REASON": 422,
    "INVALID_TASK_STATE": 409, "UNRESOLVED_REVIEW_ITEMS": 409,
    "STAGE_FAILURE": 422,
    "TEMPLATE_NOT_FOUND": 404,
    "TEMPLATE_RULE_NOT_FOUND": 404,
    "TEMPLATE_FORMAT_UNSUPPORTED": 422,
    "TEMPLATE_FILE_MISSING": 422,
    "TEMPLATE_FILE_EMPTY": 422,
    "TEMPLATE_METADATA_INVALID": 422,
    "TEMPLATE_RULE_INVALID": 422,
    "TEMPLATE_RULE_UPDATE_INVALID": 422,
    "TEMPLATE_VERSION_EXISTS": 409,
    "TEMPLATE_IMMUTABLE": 409,
    "TEMPLATE_STATE_INVALID": 409,
    "TEMPLATE_PUBLISH_BLOCKED": 409,
    "AUTHENTICATION_REQUIRED": 401,
    "PERMISSION_DENIED": 403,
}


def error_response(code: str, message: str, details: dict | None = None, status_code: int | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code or _STATUS.get(code, 500), content={"error": {"code": code, "message": message, "details": details or {}}})


async def lifecycle_error_handler(_request: Request, error: LifecycleError) -> JSONResponse:
    return error_response(error.code, str(error), error.details)


async def template_error_handler(_request: Request, error: TemplateServiceError) -> JSONResponse:
    return error_response(error.code, error.message, error.details)


async def access_error_handler(_request: Request, error: AccessError) -> JSONResponse:
    return error_response(error.code, error.message)


async def request_validation_error_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
    """Do not leak framework-shaped validation details through the public API."""
    fields = {str(part) for item in error.errors() for part in item.get("loc", ())}
    if "reason" in fields:
        return error_response("INVALID_REASON", "manual decision reason is required", status_code=422)
    if "final_status" in fields:
        return error_response("INVALID_STATUS", "manual final status is invalid", status_code=422)
    return error_response("INVALID_UPLOAD", "request data is invalid", status_code=422)
