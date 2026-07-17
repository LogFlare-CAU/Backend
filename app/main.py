import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    FastAPI,
    Request,
    status,
)
from fastapi import (
    HTTPException as FastAPIHTTPException,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.env_utils import getenvval
from common.fcm import init as fcm_init
from common.logger_setup import get_logger, setup_uvicorn_file_logging
from common.schema import ErrorResponse

# ===========================================================================
title = "LogFlare API"
version = "1.0.0"
description = "LogFlare API 서버"
# ===============================공통 초기화================================
setup_uvicorn_file_logging()
logger = get_logger()
fcm_init()
_INDEX_HTML = Path(__file__).resolve().parent / "res" / "index.html"
with open(_INDEX_HTML, "r", encoding="utf-8") as f:
    index_html_content = f.read()
# ===========================INCLUE ROUTERS HERE===========================
from routes import fcm, logs, projects, user


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 초기화 작업
    fcm.init()
    await user.init_superuser()
    yield
    # 앱 종료 시 정리 작업

root_path = getenvval("LOGFLARE_API_ROOT_PATH", "")
app = FastAPI(title=title, version=version, description=description, lifespan=lifespan, root_path=root_path, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(user.router)
app.include_router(projects.router)
app.include_router(logs.router)
app.include_router(fcm.router)
# ===========================================================================


@app.get("/")
def read_root(request: Request):
    return HTMLResponse(content=index_html_content, status_code=200)


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
    logger.error("Database integrity error: %s", exc)
    return _build_error(
        status.HTTP_409_CONFLICT,
        "Database integrity error (duplicate or constraint violation).",
        data=None,
    )


# --- 검증 실패 422 ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Request validation error: %s", exc.errors())
    return _build_error(
        getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", status.HTTP_422_UNPROCESSABLE_ENTITY),
        "Request validation error.",
        data={"errors": jsonable_encoder(exc.errors())},
    )


# --- 알 수 없는 에러 500 ---
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("Unhandled exception:\n%s", tb)
    return _build_error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An unexpected server error occurred.",
        data=None,
    )


# ===========================================================================
if __name__ == "__main__":
    import uvicorn

    port = getenvval("LOGFLARE_API_PORT", 80)
    logger.info("Server is UP")
    uvicorn.run(app, host="0.0.0.0", port=port)
