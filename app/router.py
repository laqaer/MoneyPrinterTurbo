"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints. Every V1 route is privileged: it
can spend provider credits, read task state, upload media, or mutate generated
artifacts, so authentication is applied once at the root inclusion boundary.
"""

from fastapi import APIRouter, Depends

from app.controllers import base
from app.controllers.v1 import llm, video

root_api_router = APIRouter()
_auth = [Depends(base.verify_token)]
root_api_router.include_router(video.router, dependencies=_auth)
root_api_router.include_router(llm.router, dependencies=_auth)
