import os
import secrets
from pathlib import Path

import uvicorn
from loguru import logger

from app.config import config
from app.controllers.base import configured_api_key


MIN_API_KEY_LENGTH = 32


def listen_host() -> str:
    """Keep ordinary launches local unless an operator explicitly opts out."""
    override = os.getenv("MPT_LISTEN_HOST", "").strip()
    if override:
        return override
    configured = str(config.listen_host).strip()
    if configured in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    return configured


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "::1", "localhost"}


def _read_or_create_api_key(path: Path) -> str:
    """Return a persistent key from a mode-0600 file, creating it atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        value = secrets.token_urlsafe(32)
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            # Another reload/process won the creation race. Reuse its key.
            value = path.read_text(encoding="utf-8").strip()
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(value + "\n")

    if len(value) < MIN_API_KEY_LENGTH:
        raise RuntimeError(
            f"API key file {path} must contain at least {MIN_API_KEY_LENGTH} characters"
        )

    try:
        path.chmod(0o600)
    except OSError:
        # Some mounted/Windows filesystems do not implement POSIX modes. The
        # secret remains outside source control and authentication still holds.
        pass
    return value


def ensure_api_key(host: str) -> None:
    """Bootstrap safe local installs while requiring intent for network binds.

    Deployments may supply MPT_API_KEY directly. Fresh local installs receive a
    persistent random key in storage/.mpt_api_key. Container deployments opt in
    to the same behavior with MPT_API_KEY_FILE, whose path is on the mounted
    storage volume. A non-loopback bind without either explicit mechanism is a
    startup error rather than an unauthenticated or unusable service.
    """
    if configured_api_key():
        return

    configured_file = os.getenv("MPT_API_KEY_FILE", "").strip()
    if configured_file:
        key_path = Path(configured_file).expanduser()
    elif _is_loopback_host(host):
        key_path = Path.cwd() / "storage" / ".mpt_api_key"
    else:
        raise RuntimeError(
            "MPT_API_KEY or MPT_API_KEY_FILE is required for a non-loopback API bind"
        )

    os.environ["MPT_API_KEY"] = _read_or_create_api_key(key_path)
    logger.warning(
        "API authentication key loaded from %s; send it in the X-API-Key header",
        key_path,
    )


if __name__ == "__main__":
    host = listen_host()
    ensure_api_key(host)
    logger.info(f"start server on {host}:{config.listen_port}, docs: /docs")
    uvicorn.run(
        app="app.asgi:app",
        host=host,
        port=config.listen_port,
        reload=config.reload_debug,
        log_level="warning",
    )
