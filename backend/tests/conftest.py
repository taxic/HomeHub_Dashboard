from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app

PASSWORD = "correct horse battery staple"


def make_settings(tmp_path, **overrides) -> Settings:
    base = dict(
        environment="test",
        data_dir=tmp_path,
        secret_key="x" * 48,
        monitor_enabled=False,
        cookie_secure=False,
        docker_enabled=False,
        login_max_failures=5,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
async def app(tmp_path):
    application = create_app(make_settings(tmp_path))
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"user-agent": "pytest"}
    ) as c:
        yield c


@pytest.fixture
async def auth(client):
    """Create the admin user and return Authorization headers."""
    r = await client.post("/api/v1/auth/setup", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": PASSWORD, "client": "mobile"}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def fake_docker():
    from tests.fakes import FakeDocker, make_container

    return FakeDocker(
        [
            make_container("plex"),
            make_container("navidrome"),
            make_container("pihole", health="healthy"),
            make_container("homelab-backend"),
            make_container("old-thing", state="exited"),
        ]
    )


@pytest.fixture
async def mon(app, fake_docker):
    """A Monitor wired to fakes. Loops are not started; tests drive refresh methods directly."""
    import httpx

    from app.monitoring.healthcheck import HealthChecker
    from app.monitoring.monitor import Monitor

    state = {"handler": lambda request: httpx.Response(200)}
    transport = httpx.MockTransport(lambda request: state["handler"](request))
    m = Monitor(app.state.ctx, docker=fake_docker, checker=HealthChecker(transport=transport))
    m.http_state = state  # tests replace m.http_state["handler"]
    app.state.ctx.monitor = m
    return m
