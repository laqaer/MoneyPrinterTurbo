import os
import secrets
from uuid import uuid4

from fastapi import Request

from app.config import config
from app.models.exception import HttpException


def get_task_id(request: Request):
    task_id = request.headers.get("x-task-id")
    if not task_id:
        task_id = uuid4()
    return str(task_id)


def get_api_key(request: Request):
    return request.headers.get("x-api-key")


def configured_api_key() -> str:
    """Prefer deployment injection; retain config.toml compatibility."""
    environment_value = os.getenv("MPT_API_KEY", "").strip()
    if environment_value:
        return environment_value
    value = config.app.get("api_key", "")
    return value.strip() if isinstance(value, str) else ""


def verify_token(request: Request):
    """Fail closed unless the request matches a non-empty configured key."""
    request_id = get_task_id(request)
    expected = configured_api_key()
    if not expected:
        raise HttpException(
            task_id=request_id,
            status_code=503,
            message="API authentication is not configured",
        )

    provided = get_api_key(request)
    if not isinstance(provided, str) or not secrets.compare_digest(provided, expected):
        raise HttpException(
            task_id=request_id,
            status_code=401,
            message="invalid API token",
        )
