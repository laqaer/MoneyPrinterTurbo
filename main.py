import os

import uvicorn
from loguru import logger

from app.config import config


def listen_host() -> str:
    """Keep ordinary launches local unless an operator explicitly opts out."""
    override = os.getenv("MPT_LISTEN_HOST", "").strip()
    if override:
        return override
    configured = str(config.listen_host).strip()
    if configured in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    return configured


if __name__ == "__main__":
    host = listen_host()
    logger.info(f"start server on {host}:{config.listen_port}, docs: /docs")
    uvicorn.run(
        app="app.asgi:app",
        host=host,
        port=config.listen_port,
        reload=config.reload_debug,
        log_level="warning",
    )
