"""Helpers for serving the static frontend from FastAPI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _resolve_frontend_dir() -> Path | None:
    backend_root = Path(__file__).resolve().parents[1]
    candidates = [
        backend_root.parent / "frontend",
        backend_root / "frontend",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def mount_frontend(app: FastAPI) -> None:
    """Serve the static site from the FastAPI app."""
    frontend_dir = _resolve_frontend_dir()

    if frontend_dir is None:
        logger.warning(
            "Frontend directory not found",
            checked_paths=[
                str(Path(__file__).resolve().parents[1].parent / "frontend"),
                str(Path(__file__).resolve().parents[1] / "frontend"),
            ],
        )

        @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
        async def root_redirect_missing_frontend() -> RedirectResponse:
            return RedirectResponse(url=settings.frontend_url, status_code=307)

        return

    pages_dir = frontend_dir / "pages"
    assets_dir = frontend_dir / "assets"
    env_js_path = frontend_dir / "env.js"
    favicon_path = frontend_dir / "favicon.svg"

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/pages/index.html", status_code=307)

    @app.api_route("/pages", methods=["GET", "HEAD"], include_in_schema=False)
    @app.api_route("/pages/", methods=["GET", "HEAD"], include_in_schema=False)
    async def pages_redirect() -> RedirectResponse:
        return RedirectResponse(url="/pages/index.html", status_code=307)

    @app.get("/favicon.svg", include_in_schema=False)
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        if not favicon_path.exists():
            return Response(status_code=204)
        return FileResponse(favicon_path, media_type="image/svg+xml")

    @app.get("/env.js", include_in_schema=False)
    async def frontend_env() -> Response:
        if not env_js_path.exists():
            logger.warning("Frontend env.js not found", path=str(env_js_path))
            return Response(status_code=404)
        return FileResponse(env_js_path, media_type="text/javascript; charset=utf-8")

    if pages_dir.exists():
        app.mount("/pages", StaticFiles(directory=pages_dir), name="frontend-pages")
    else:
        logger.warning("Frontend pages directory not found", path=str(pages_dir))

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")
    else:
        logger.warning("Frontend assets directory not found", path=str(assets_dir))
