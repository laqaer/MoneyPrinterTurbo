import os
import runpy
from pathlib import Path
from unittest.mock import patch

from app.config import config


ROOT_DIR = Path(__file__).resolve().parent.parent


def _run_main(configured_host: str, environment_host: str = ""):
    with (
        patch.object(config, "listen_host", configured_host),
        patch.object(config, "listen_port", 8765),
        patch.object(config, "reload_debug", True),
        patch.dict(os.environ, {"MPT_LISTEN_HOST": environment_host}),
        patch("uvicorn.run") as run_server,
    ):
        runpy.run_path(str(ROOT_DIR / "main.py"), run_name="__main__")
    return run_server


def test_main_preserves_an_explicit_loopback_config():
    run_server = _run_main("127.0.0.1")
    run_server.assert_called_once_with(
        app="app.asgi:app",
        host="127.0.0.1",
        port=8765,
        reload=True,
        log_level="warning",
    )


def test_main_does_not_inherit_an_all_interfaces_example_default():
    run_server = _run_main("0.0.0.0")
    assert run_server.call_args.kwargs["host"] == "127.0.0.1"


def test_non_loopback_binding_requires_an_explicit_environment_override():
    run_server = _run_main("127.0.0.1", "0.0.0.0")
    assert run_server.call_args.kwargs["host"] == "0.0.0.0"
