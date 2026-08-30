import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import config
from app.controllers import base
from app.controllers.v1.base import new_router
from app.models.exception import HttpException


class TestControllerAuthentication(unittest.TestCase):
    def setUp(self):
        self.original_app_config = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app_config)

    @staticmethod
    def _request(headers=None):
        return SimpleNamespace(
            headers=headers or {},
            url="http://localhost/api/v1/tasks",
        )

    def test_get_task_id_reuses_header_or_generates_uuid(self):
        """客户端 request ID 原样保留，缺失时生成可追踪 UUID。"""
        self.assertEqual(
            base.get_task_id(self._request({"x-task-id": "request-123"})),
            "request-123",
        )

        generated = base.get_task_id(self._request())
        self.assertEqual(len(generated), 36)
        self.assertEqual(generated.count("-"), 4)

    def test_verify_token_accepts_matching_config_key(self):
        config.app["api_key"] = "secret"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MPT_API_KEY", None)
            result = base.verify_token(self._request({"x-api-key": "secret"}))
        self.assertIsNone(result)

    def test_environment_key_takes_precedence_over_config_file(self):
        config.app["api_key"] = "stale-config-key"
        with patch.dict(os.environ, {"MPT_API_KEY": "deployment-key"}):
            self.assertIsNone(
                base.verify_token(self._request({"x-api-key": "deployment-key"}))
            )
            with self.assertRaises(HttpException) as raised:
                base.verify_token(self._request({"x-api-key": "stale-config-key"}))
            self.assertEqual(raised.exception.status_code, 401)

    def test_verify_token_fails_closed_when_no_key_is_configured(self):
        config.app.pop("api_key", None)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MPT_API_KEY", None)
            for headers in ({}, {"x-api-key": ""}):
                with self.subTest(headers=headers):
                    with self.assertRaises(HttpException) as raised:
                        base.verify_token(self._request(headers))
                    self.assertEqual(raised.exception.status_code, 503)
                    self.assertIn("not configured", raised.exception.message)

    def test_verify_token_rejects_missing_or_wrong_key(self):
        config.app["api_key"] = "secret"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MPT_API_KEY", None)
            for provided_key in (None, "wrong"):
                with self.subTest(provided_key=provided_key):
                    headers = {"x-task-id": "auth-request"}
                    if provided_key is not None:
                        headers["x-api-key"] = provided_key

                    with self.assertRaises(HttpException) as raised:
                        base.verify_token(self._request(headers))

                    self.assertEqual(raised.exception.status_code, 401)
                    self.assertEqual(raised.exception.message, "invalid API token")

    def test_new_router_preserves_common_prefix_and_dependencies(self):
        dependency = object()

        plain_router = new_router()
        protected_router = new_router(dependencies=[dependency])

        self.assertEqual(plain_router.prefix, "/api/v1")
        self.assertEqual(plain_router.tags, ["V1"])
        self.assertEqual(protected_router.dependencies, [dependency])

    def test_every_registered_v1_route_has_the_authentication_dependency(self):
        # Import late so the assertion inspects the assembled root router rather
        # than only the helper used to construct each child router.
        from app.router import root_api_router

        self.assertGreater(len(root_api_router.routes), 0)
        for route in root_api_router.routes:
            calls = [dependency.call for dependency in route.dependant.dependencies]
            self.assertIn(base.verify_token, calls, route.path)


if __name__ == "__main__":
    unittest.main()
