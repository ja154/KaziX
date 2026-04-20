"""
app/main.py
───────────
FastAPI application factory.
All routers, middleware, and startup hooks are wired here.
"""

import asyncio
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter
from slowapi.util import get_remote_address

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
            allowed_hosts=["api.kazix.co.ke", "*.kazix.co.ke"],
        )

    # ── Prometheus metrics (/metrics) ───────────────────────
    Instrumentator().instrument(app).expose(app)

    # ── Routers ─────────────────────────────────────────────
    from app.api.v1 import router as v1_router
    app.include_router(v1_router, prefix="/v1")

    # ── Health probe ─────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    @limiter.limit("10/minute")
    async def health(request: Request):
        return {"status": "ok", "env": settings.app_env}

    # ── Frontend pages/assets ───────────────────────────────
    mount_frontend(app)

    return app


app = create_app()
