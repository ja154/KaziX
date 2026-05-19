from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import web as web_module
from app.main import app as main_app


def test_root_redirects_to_frontend_index() -> None:
    with TestClient(main_app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/pages/index.html"


def test_frontend_page_is_served_from_fastapi() -> None:
    with TestClient(main_app) as client:
        response = client.get("/pages/login.html")

    assert response.status_code == 200
    assert "Sign In" in response.text


def test_frontend_assets_are_served_from_fastapi() -> None:
    with TestClient(main_app) as client:
        response = client.get("/assets/css/styles.css")

    assert response.status_code == 200
    assert ":root" in response.text


def test_frontend_env_js_is_served_from_fastapi() -> None:
    with TestClient(main_app) as client:
        response = client.get("/env.js")

    assert response.status_code == 200
    assert "window.KAZIX_CONFIG" in response.text


@pytest.mark.asyncio
async def test_mount_frontend_uses_frontend_redirects_in_production_when_assets_missing(monkeypatch) -> None:
    log_calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(web_module, "_resolve_frontend_dir", lambda: None)
    monkeypatch.setattr(
        web_module,
        "settings",
        SimpleNamespace(
            is_production=True,
            frontend_url="https://kazixfrontend.vercel.app",
        ),
    )
    monkeypatch.setattr(
        web_module,
        "logger",
        SimpleNamespace(
            info=lambda message, **kwargs: log_calls.append((message, kwargs)),
            warning=lambda *args, **kwargs: None,
        ),
    )

    app = FastAPI()
    web_module.mount_frontend(app)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        root_response = await client.get("/", follow_redirects=False)
        pages_response = await client.get("/pages", follow_redirects=False)

    assert root_response.status_code == 307
    assert root_response.headers["location"] == "https://kazixfrontend.vercel.app"
    assert pages_response.status_code == 307
    assert pages_response.headers["location"] == "https://kazixfrontend.vercel.app/pages/index.html"
    assert len(log_calls) == 1
    message, kwargs = log_calls[0]
    assert message == "Embedded frontend assets not bundled; serving API-only backend as expected in production"
    assert kwargs["frontend_url"] == "https://kazixfrontend.vercel.app"
    assert len(kwargs["checked_paths"]) == 2
    assert all(path.endswith("/frontend") for path in kwargs["checked_paths"])
