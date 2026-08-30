import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.asgi import app
from app.config import config


ROOT = Path(__file__).resolve().parents[2]


def test_privileged_v1_routes_require_authentication():
    original = dict(config.app)
    try:
        config.app["api_key"] = "test-request-credential"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MPT_API_KEY", None)
            client = TestClient(app)
            missing = client.get("/api/v1/tasks")
            wrong = client.get(
                "/api/v1/tasks", headers={"x-api-key": "wrong"}
            )
            allowed = client.get(
                "/api/v1/tasks",
                headers={"x-api-key": "test-request-credential"},
            )

        assert missing.status_code == 401
        assert wrong.status_code == 401
        assert allowed.status_code == 200
    finally:
        config.app.clear()
        config.app.update(original)


def test_generated_task_files_use_the_same_authentication_boundary():
    original = dict(config.app)
    try:
        config.app["api_key"] = "test-request-credential"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MPT_API_KEY", None)
            client = TestClient(app)
            missing = client.get("/tasks/not-present.mp4")
            wrong = client.get(
                "/tasks/not-present.mp4", headers={"x-api-key": "wrong"}
            )
            authenticated = client.get(
                "/tasks/not-present.mp4",
                headers={"x-api-key": "test-request-credential"},
            )

        assert missing.status_code == 401
        assert wrong.status_code == 401
        assert authenticated.status_code == 404
    finally:
        config.app.clear()
        config.app.update(original)


def test_unconfigured_authentication_fails_closed():
    original = dict(config.app)
    try:
        config.app.pop("api_key", None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MPT_API_KEY", None)
            response = TestClient(app).get("/api/v1/tasks")
        assert response.status_code == 503
    finally:
        config.app.clear()
        config.app.update(original)


def test_release_compose_builds_reviewed_source_and_requires_api_key():
    compose = (ROOT / "docker-compose.release.yml").read_text(encoding="utf-8")
    assert "ghcr.io/harry0703/moneyprinterturbo:latest" not in compose
    assert "build: *common-build" in compose
    assert "image: moneyprinterturbo:local" in compose
    assert "MPT_API_KEY: ${MPT_API_KEY:?" in compose
    assert 'MPT_LISTEN_HOST: 0.0.0.0' in compose
    assert '"127.0.0.1:8080:8080"' in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose
