"""
app/main.py
───────────
FastAPI application factory.
All routers, middleware, and startup hooks are wired here.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.web import mount_frontend

limiter = Limiter(key_func=get_remote_address)

logger = get_logger(__name__)
settings = get_settings()

# ── Background tasks ────────────────────────────────────────
_otp_queue_task: asyncio.Task | None = None


async def _otp_queue_worker():
    """Background worker to process queued OTP dispatches with retry logic."""
    from app.services.otp import process_otp_queue_periodic

    logger.info("OTP queue worker started")
    try:
        while True:
            try:
                await process_otp_queue_periodic()
            except Exception as exc:
                logger.error("Error processing OTP queue", error=str(exc))
            # Process queue every 2 seconds
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        logger.info("OTP queue worker stopped")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    global _otp_queue_task
    
    configure_logging()
    logger.info(
        "KaziX API starting",
        env=settings.app_env,
        port=settings.app_port,
    )

    # Start OTP queue worker
    _otp_queue_task = asyncio.create_task(_otp_queue_worker())

    yield

    # Shutdown: cancel OTP queue worker
    if _otp_queue_task:
        _otp_queue_task.cancel()
        try:
            await _otp_queue_task
        except asyncio.CancelledError:
            pass

    logger.info("KaziX API shutting down")


def create_app() -> FastAPI:
    if settings.is_production and settings.app_secret_key:
        sentry_sdk.init(
            dsn="",   # Set SENTRY_DSN in .env when ready
            environment=settings.app_env,
            traces_sample_rate=0.2,
        )

    app = FastAPI(
        title="KaziX API",
        description="Backend API for KaziX — Kenya's skilled-worker marketplace.",
        version="1.0.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        lifespan=lifespan,
    )

    # ── Middleware ──────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "Authorization"],
        max_age=86400,
    )

    # Security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self' https: data:; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https:"
        return response

    app.state.limiter = limiter

    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.trusted_hosts,
        )

    # ── Prometheus metrics (/metrics) ───────────────────────
    Instrumentator().instrument(app).expose(app)

    # ── Exception handlers ──────────────────────────────────
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """
        Handle HTTP exceptions with user-friendly error responses.
        Maps technical errors to messages safe for frontend display.
        """
        status_code = exc.status_code
        detail = exc.detail or "An error occurred"

        # Build user-friendly error response
        error_response: dict[str, Any] = {
            "error": _get_error_code_from_status(status_code),
            "message": detail if isinstance(detail, str) else str(detail),
            "status_code": status_code,
        }

        # Add details array for validation errors
        if isinstance(detail, list):
            error_response["details"] = detail
        elif isinstance(detail, dict):
            # Already structured detail
            error_response.update(detail)

        # Log the error for debugging
        logger.warning(
            "HTTP exception",
            status_code=status_code,
            detail=str(detail),
            path=str(request.url),
        )

        return JSONResponse(status_code=status_code, content=error_response)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Handle validation errors with structured field-level error messages.
        """
        # Extract field-level validation errors
        details = []
        field_errors = {}

        for error in exc.errors():
            field_path = ".".join(str(x) for x in error["loc"][1:])  # Skip "body"
            field_errors[field_path] = error["msg"]
            details.append(
                {
                    "field": field_path,
                    "message": error["msg"],
                    "type": error["type"],
                }
            )

        error_response = {
            "error": "validation_error",
            "message": "Please check your input and try again.",
            "status_code": 422,
            "details": details,
            "field_errors": field_errors,
        }

        logger.info(
            "Validation error",
            path=str(request.url),
            errors=field_errors,
        )

        return JSONResponse(status_code=422, content=error_response)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all exception handler for unexpected errors.
        Logs full details internally, returns safe message to user.
        """
        error_id = f"{request.client.host if request.client else 'unknown'}_{id(exc)}"

        # Log full error details for debugging
        logger.error(
            "Unhandled exception",
            error_id=error_id,
            path=str(request.url),
            exception=str(exc),
            exc_info=True,
        )

        # Return safe error message to user
        error_response = {
            "error": "internal_server_error",
            "message": "Something went wrong. Our team has been notified.",
            "status_code": 500,
            "error_id": error_id,  # For user to report to support
        }

        # In production, send to Sentry via logger
        if settings.is_production:
            sentry_sdk.capture_exception(exc)

        return JSONResponse(status_code=500, content=error_response)

    def _get_error_code_from_status(status_code: int) -> str:
        """
        Map HTTP status code to error code string for frontend.
        """
        status_to_code = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            429: "too_many_requests",
            500: "internal_server_error",
            502: "bad_gateway",
            503: "service_unavailable",
        }
        return status_to_code.get(status_code, f"error_{status_code}")

    # ── Routers ─────────────────────────────────────────────
    from app.api.v1 import router as v1_router
    app.include_router(v1_router, prefix="/v1")

    # ── Health probe ─────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    async def health():
        # Render probes health endpoints every few seconds during deploys
        # and while the service is running, so this route must never be
        # subject to app-level rate limiting.
        return {"status": "ok", "env": settings.app_env}

    # ── Frontend pages/assets ───────────────────────────────
    mount_frontend(app)

    return app


app = create_app()
