import asyncio
import json
import os
import tempfile
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

import httpx
import app

REAL_ASYNC_CLIENT = httpx.AsyncClient


class ScenarioEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = os.path.join(self.temp_dir.name, "scenario-tests.db")
        self.url_patch = patch.object(app, "safe_url", side_effect=lambda value: urlsplit(value))
        self.url_patch.start()
        app.init_db()
        self.uid = "test-owner"
        with app.db() as conn:
            conn.execute("INSERT INTO users VALUES(?,?,?,?)", (self.uid, "scenario-tests@example.test", "unused", app.now()))
        self.monitor = app.create_monitor(app.MonitorInput(name="scenario tests", url="https://api.example.test/"), self.uid)
        self.real_async_client = REAL_ASYNC_CLIENT

    def tearDown(self):
        app.httpx.AsyncClient = REAL_ASYNC_CLIENT
        self.url_patch.stop()
        app.DB = self.old_db
        self.temp_dir.cleanup()

    def make_case(self, **changes):
        payload = {"name": "engine test", "url": "https://api.example.test/run", "is_active": False, **changes}
        data = app.TestCaseInput.model_validate(payload)
        return app.create_test_case(self.monitor["id"], data, self.uid)

    def mock_transport(self, handler):
        app.httpx.AsyncClient = lambda **kwargs: self.real_async_client(transport=httpx.MockTransport(handler), **kwargs)

    async def test_post_then_authenticated_get_and_saved_step_results(self):
        with patch.dict(os.environ, {"SENTINEL_SECRET_BOOTSTRAP": "Bearer bootstrap", "SENTINEL_SECRET_PASSWORD": "not-stored-password"}):
            def handler(request):
                if request.method == "POST":
                    self.assertEqual(request.headers["authorization"], "Bearer bootstrap")
                    self.assertEqual(json.loads(request.content)["password"], "not-stored-password")
                    return httpx.Response(201, json={"id": 41, "access_token": "one-time-token"})
                self.assertEqual(request.url.path, "/users/41")
                self.assertEqual(request.headers["authorization"], "Bearer one-time-token")
                return httpx.Response(200, json={"active": True})

            self.mock_transport(handler)
            case = self.make_case(
                method="POST", expected_status=201, allow_mutation=True,
                request_body='{"password":"{{env:SENTINEL_SECRET_PASSWORD}}"}',
                headers={"Authorization": "env:SENTINEL_SECRET_BOOTSTRAP"},
                extract={"user_id": "id", "access_token": "access_token"},
                steps=[{"name": "fetch created user", "url": "https://api.example.test/users/{{user_id}}", "headers": {"Authorization": "Bearer {{access_token}}"}, "assertions": [{"path": "active", "operator": "equals", "value": True}]}],
            )
            result = await app.run_test_case(app.owned_test_case(case["id"], self.uid))
            self.assertEqual(result["outcome"], "UP")
            self.assertEqual([step["method"] for step in result["steps"]], ["POST", "GET"])
            history = app.test_case_history(case["id"], 50, self.uid)["items"]
            self.assertEqual(len(history[0]["step_results"]), 2)
            self.assertNotIn("one-time-token", json.dumps(history))

    async def test_all_methods_and_mutation_guards(self):
        self.mock_transport(lambda request: httpx.Response(200, json={"ok": True}))
        for method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                payload = {"method": method, "allow_mutation": method in app.WRITE_METHODS}
                if method in app.WRITE_METHODS:
                    payload["request_body"] = '{"demo":true}'
                case = self.make_case(**payload)
                if method in app.WRITE_METHODS:
                    with self.assertRaises(app.HTTPException) as missing_confirmation:
                        await app.run_test_case_now(case["id"], False, self.uid)
                    self.assertEqual(missing_confirmation.exception.status_code, 400)
                    result = await app.run_test_case_now(case["id"], True, self.uid)
                else:
                    result = await app.run_test_case_now(case["id"], False, self.uid)
                self.assertEqual(result["outcome"], "UP")

        with self.assertRaises(ValueError):
            app.TestCaseInput.model_validate({"name": "unsafe", "url": "https://api.example.test/", "method": "POST", "is_active": False})
        with self.assertRaises(ValueError):
            app.TestCaseInput.model_validate({"name": "scheduled write", "url": "https://api.example.test/", "method": "POST", "allow_mutation": True})

    async def test_down_invalid_json_timeout_and_oversize_outcomes(self):
        scenarios = [
            ("down", lambda request: httpx.Response(503), "DOWN"),
            ("invalid-json", lambda request: httpx.Response(200, content=b"not json"), "VALIDATION_FAILED"),
            ("timeout", lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout")), "TIMEOUT"),
            ("oversize", lambda request: httpx.Response(200, content=b"x" * (app.MAX_ASSERTION_RESPONSE_BYTES + 1)), "VALIDATION_FAILED"),
            ("connection-error", lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline")), "ERROR"),
        ]
        for name, handler, expected in scenarios:
            with self.subTest(outcome=expected):
                self.mock_transport(handler)
                case = self.make_case(name=name, assertions=[{"path": "state", "operator": "equals", "value": "ok"}])
                result = await app.run_test_case(app.owned_test_case(case["id"], self.uid))
                self.assertEqual(result["outcome"], expected)


if __name__ == "__main__":
    unittest.main()
