import logging
import traceback

from fastapi import FastAPI, Request, status, Response, HTTPException as FastAPIHTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from common.logger_setup import setup_uvicorn_file_logging
from common.schema import ErrorResponse

# ===========================================================================
app = FastAPI()
logger = logging.getLogger("logflare")
# ===========================INCLUE ROUTERS HERE===========================
from routes import user
app.include_router(user.router)
# ===========================================================================

@app.get("/")
def read_root(request: Request):
    host = request.client.host
    return {"Hello": "World", "host": host}

# ===============================ERROR HANDLING==============================
# 모든 HTTP 예외
def _build_error(status_code: int, message: str, data=None) -> ErrorResponse:
    return ErrorResponse(message=message, error_code=status_code, data=data)

@app.exception_handler(FastAPIHTTPException)
async def fastapi_http_exception_handler(request: Request, exc: FastAPIHTTPException, response: Response):
    response.status_code = exc.status_code
    msg = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return _build_error(exc.status_code, msg, None if isinstance(exc.detail, str) else exc.detail)

@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException, response: Response):
    response.status_code = exc.status_code
    msg = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return _build_error(exc.status_code, msg, None if isinstance(exc.detail, str) else exc.detail)

# 무결성 제약(중복 등)
@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError, response: Response):
    logger.error(f"IntegrityError on {request.method} {request.url}\nError: {str(exc)}")
    response.status_code = status.HTTP_409_CONFLICT
    return ErrorResponse(
        message="Database integrity error (duplicate or constraint violation).",
        error_code=409,
        data=str(exc.orig) if getattr(exc, "orig", None) else str(exc),
    )

# 검증 에러(422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError, response: Response):
    logger.error(
        f"422 Validation Error on {request.method} {request.url}\n"
        f"Errors: {exc.errors()}\n"
        f"Body: {exc.body}"
    )
    response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return ErrorResponse(
        message="Request validation error.",
        error_code=422,
        data={"errors": exc.errors(), "body": exc.body},
    )

# 알 수 없는 모든 에러(500)
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception, response: Response):
    tb = traceback.format_exc()
    logger.error(f"500 on {request.method} {request.url}\n{tb}")
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return ErrorResponse(
        message="An unexpected server error occurred.",
        error_code=500,
        data={"traceback": tb},  # 운영에선 노출 최소화 권장
    )

if __name__ == "__main__":
    import uvicorn
    setup_uvicorn_file_logging()
    logger.info("Server is UP")
    uvicorn.run(app, host="0.0.0.0", port=8265)