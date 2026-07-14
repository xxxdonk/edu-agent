from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorDetail, ErrorResponse


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            detail = ErrorDetail.model_validate(exc.detail)
        else:
            detail = ErrorDetail(
                code="HTTP_ERROR",
                message=str(exc.detail),
                details={},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(error=detail).model_dump(mode="json"),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        response = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="请求数据不符合 API 契约",
                details={"validation_errors": jsonable_encoder(exc.errors())},
            )
        )
        return JSONResponse(
            status_code=422,
            content=response.model_dump(mode="json"),
        )
