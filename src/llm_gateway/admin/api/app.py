"""Separate FastAPI application served only by the private listener."""

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_gateway.admin.api import catalog, identity, limits, organizations, policies, reports
from llm_gateway.admin.api.auth import AdminContext, authenticate
from llm_gateway.errors import (
    GatewayError,
    error_body,
    gateway_error_handler,
    http_exception_handler,
)


def create_admin_app(context: AdminContext) -> FastAPI:
    app = FastAPI(title="LLM Gateway Admin", version="1")
    app.state.admin_context = context
    router = APIRouter(prefix="/admin/v1", dependencies=[Depends(authenticate)])
    for module in (catalog, identity, limits, organizations, policies, reports):
        router.include_router(module.router)
    app.include_router(router)
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(ValueError, _value_error)
    app.add_exception_handler(PermissionError, _permission_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.add_exception_handler(Exception, _unexpected_error)
    return app


async def _value_error(_: Request, exc: Exception) -> JSONResponse:
    message = str(exc)
    missing = message.endswith("not found")
    return JSONResponse(
        error_body(
            message,
            type="invalid_request_error",
            code="not_found" if missing else "invalid_request",
        ),
        status_code=404 if missing else 400,
    )


async def _permission_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        error_body(str(exc), type="invalid_request_error", code="forbidden"), status_code=403
    )


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        error_body("Invalid admin request.", type="invalid_request_error", code="invalid_request"),
        status_code=400,
    )


async def _integrity_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        error_body(
            "Administrative resource already exists.",
            type="invalid_request_error",
            code="conflict",
        ),
        status_code=409,
    )


async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        error_body("Administrative request failed.", type="server_error", code="internal_error"),
        status_code=500,
    )
