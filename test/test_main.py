import os
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from app.config import config


ROOT_DIR = Path(__file__).resolve().parent.parent
TEST_API_KEY = "test-api-key-with-at-least-thirty-two-characters"


def _load_main():
    return runpy.run_path(str(ROOT_DIR / "main.py"), run_name="mpt_main_test")


def _run_main(configured_host: str, environment_host: str = ""):
    with (
        patch.object(config, "listen_host", configured_host),
        patch.object(config, "listen_port", 8765),
        patch.object(config, "reload_debug", True),
        patch.dict(
            os.environ,
            {
                "MPT_LISTEN_HOST": environment_host,
                "MPT_API_KEY": TEST_API_KEY,
                "MPT_API_KEY_FILE": "",
            },
        ),
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


def test_fresh_local_launch_bootstraps_and_reuses_a_persistent_api_key():
    functions = _load_main()
    ensure_api_key = functions["ensure_api_key"]

    with TemporaryDirectory() as directory:
        key_file = Path(directory) / "api.key"
        with (
            patch.dict(
                os.environ,
                {"MPT_API_KEY": "", "MPT_API_KEY_FILE": str(key_file)},
            ),
            patch.dict(config.app, {"api_key": ""}),
        ):
            ensure_api_key("127.0.0.1")
            first = os.environ["MPT_API_KEY"]
            assert len(first) >= 32
            assert key_file.read_text(encoding="utf-8").strip() == first

            os.environ["MPT_API_KEY"] = ""
            ensure_api_key("127.0.0.1")
            assert os.environ["MPT_API_KEY"] == first


def test_non_loopback_launch_without_a_key_or_bootstrap_file_fails_closed():
    functions = _load_main()
    ensure_api_key = functions["ensure_api_key"]

    with (
        patch.dict(
            os.environ,
            {"MPT_API_KEY": "", "MPT_API_KEY_FILE": ""},
        ),
        patch.dict(config.app, {"api_key": ""}),
    ):
        with pytest.raises(RuntimeError, match="required for a non-loopback"):
            ensure_api_key("0.0.0.0")


def test_short_bootstrap_file_is_rejected_instead_of_weakening_authentication():
    functions = _load_main()
    ensure_api_key = functions["ensure_api_key"]

    with TemporaryDirectory() as directory:
        key_file = Path(directory) / "api.key"
        key_file.write_text("too-short\n", encoding="utf-8")
        with (
            patch.dict(
                os.environ,
                {"MPT_API_KEY": "", "MPT_API_KEY_FILE": str(key_file)},
            ),
            patch.dict(config.app, {"api_key": ""}),
        ):
            with pytest.raises(RuntimeError, match="at least 32 characters"):
                ensure_api_key("127.0.0.1")
