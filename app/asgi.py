"""Application implementation - ASGI."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import config
from app.controllers import base
from app.models.exception import HttpException
from app.router import root_api_router
from app.utils import utils


@asynccontextmanager
async def application_lifespan(_: FastAPI):
    """集中处理 API 进程启动恢复和关闭日志。"""
    logger.info("startup event")

    # 跨平台发布由当前进程线程池执行，不会在服务重启后恢复。启动时把 Redis
    # 中确认已失去执行进程的活动状态收敛为失败，避免任务永久无法删除。
    from app.services import task as task_service

    task_service.recover_interrupted_cross_posts()
    try:
        yield
    finally:
        logger.info("shutdown event")


def exception_handler(request: Request, error: HttpException):
    return JSONResponse(
        status_code=error.status_code,
        content=utils.get_response(error.status_code, error.data, error.message),
    )


def validation_exception_handler(request: Request, error: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400, data=error.errors(), message="field required"
        ),
    )


def get_application() -> FastAPI:
    """Initialize the authenticated API application."""
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
        lifespan=application_lifespan,
    )
    instance.include_router(root_api_router)
    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()

# Browser access is local-only by default. Operators exposing the API through a
# separate origin must name it explicitly rather than inheriting wildcard CORS.
configured_origins = [
    value.strip()
    for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if value.strip()
]
origins = configured_origins or [
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:8501",
    "http://localhost:8501",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Range", "X-API-Key", "X-Task-ID"],
)


@app.middleware("http")
async def protect_task_artifacts(request: Request, call_next):
    """Authenticate task files while leaving browser preflights to CORS."""
    task_path = request.url.path == "/tasks" or request.url.path.startswith(
        "/tasks/"
    )
    if task_path and request.method != "OPTIONS":
        try:
            base.verify_token(request)
        except HttpException as error:
            return exception_handler(request, error)
    return await call_next(request)


task_dir = utils.task_dir()
app.mount(
    "/tasks",
    StaticFiles(directory=task_dir, html=False, follow_symlink=False),
    name="tasks",
)

public_dir = utils.public_dir()
app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
