import asyncio
import logging
import traceback
from typing import Optional, Any

from fastapi import (
    FastAPI,
    Request,
    status,
    HTTPException as FastAPIHTTPException,
)
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from common.logger_setup import setup_uvicorn_file_logging
from common.schema import ErrorResponse
from common.env_utils import getenvval
from fastapi.responses import JSONResponse

# ===========================================================================
app = FastAPI(title="LogFlare API", version="1.0.0")
setup_uvicorn_file_logging()
logger = logging.getLogger("logflare")
# ===========================INCLUE ROUTERS HERE===========================
from routes import user, projects, logs

asyncio.run(user.init_superuser())

app.include_router(user.router)
app.include_router(projects.router)
app.include_router(logs.router)
# ===========================================================================


@app.get("/")
def read_root(request: Request):
    host = request.client.host
    return {"Hello": "World", "host": host}


# ===============================ERROR HANDLING==============================
def _build_error(
    status_code: int, message: str, data: Optional[Any] = None
) -> JSONResponse:
    err = ErrorResponse(
        success=False,
        message=message,
        error_code=status_code,
        data=data,
    )
    payload = err.model_dump(mode="json")  # v2
    return JSONResponse(status_code=status_code, content=payload)


# --- HTTPException들 (FastAPI/Starlette 각각 등록) ---
@app.exception_handler(FastAPIHTTPException)
async def fastapi_http_exception_handler(request: Request, exc: FastAPIHTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    data = None if isinstance(exc.detail, str) else exc.detail
    return _build_error(exc.status_code, msg, data)


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    msg = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    data = None if isinstance(exc.detail, str) else exc.detail
    return _build_error(exc.status_code, msg, data)


# --- 무결성 제약 위반(중복/FK 등) 409 ---
@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    # logger.error(...) 원하면 추가
    detail = getattr(exc, "orig", None)
    return _build_error(
        status.HTTP_409_CONFLICT,
        "Database integrity error (duplicate or constraint violation).",
        data=str(detail) if detail else str(exc),
    )


# --- 검증 실패 422 ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # logger.error(...) 원하면 추가
    return _build_error(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Request validation error.",
        data={"errors": exc.errors(), "body": exc.body},
    )


# --- 알 수 없는 에러 500 ---
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    # logger.error(...) 원하면 추가
    return _build_error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An unexpected server error occurred.",
        data={"traceback": tb},  # 운영환경에선 노출 최소화 권장
    )


# ===========================================================================

if __name__ == "__main__":
    import uvicorn

    port = getenvval("LOGFLARE_API_PORT", 80)
    logger.info("Server is UP")
    uvicorn.run(app, host="0.0.0.0", port=port)
