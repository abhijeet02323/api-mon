import os
import tempfile
import unittest
from unittest.mock import patch

from starlette.responses import Response

import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db = app.DB
        app.DB = os.path.join(self.temp_dir.name, "auth-tests.db")
        app.init_db()

    def tearDown(self):
        app.DB = self.old_db
        self.temp_dir.cleanup()

    def test_password_hash_is_versioned_and_legacy_hashes_still_verify(self):
        current = app.hash_password("a strong password")
        self.assertTrue(current.startswith("pbkdf2_sha256$600000$"))
        self.assertTrue(app.verify_password("a strong password", current))
        self.assertFalse(app.verify_password("incorrect password", current))
        legacy_salt = bytes.fromhex("11" * 16)
        legacy_hash = __import__("hashlib").pbkdf2_hmac("sha256", b"a strong password", legacy_salt, 310000).hex()
        self.assertTrue(app.verify_password("a strong password", legacy_salt.hex() + ":" + legacy_hash))
        self.assertFalse(app.verify_password("x", "malformed"))

    def test_login_uses_hashed_expiring_http_only_cookie_and_logout_revokes_it(self):
        created = app.register(app.Credentials(email="owner@example.test", password="a strong password"))
        self.assertEqual(created, {"created": True})
        response = Response()
        result = app.login(app.Credentials(email="OWNER@example.test", password="a strong password"), response)
        self.assertTrue(result["authenticated"])
        self.assertIn("expires_at", result)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        with open(app.DB, "rb") as database_file:
            self.assertNotIn(token, database_file.read().decode("latin1"))
        with app.db() as conn:
            session = conn.execute("SELECT token,expires_at FROM sessions").fetchone()
            user_id = conn.execute("SELECT id FROM users WHERE email=?", ("owner@example.test",)).fetchone()["id"]
        self.assertEqual(session["token"], app.session_digest(token))
        self.assertIsNotNone(session["expires_at"])

        self.assertEqual(app.current_user(None, token), user_id)

        logout_response = Response()
        app.logout(logout_response, user_id, None, token)
        with self.assertRaises(app.HTTPException):
            app.current_user(None, token)

    def test_production_cookie_is_secure_and_bad_login_is_generic(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            self.assertTrue(app.session_cookie_secure())
        with self.assertRaises(app.HTTPException) as error:
            app.login(app.Credentials(email="missing@example.test", password="a strong password"), Response())
        self.assertEqual(error.exception.status_code, 401)
        self.assertEqual(error.exception.detail, "Invalid email or password")


if __name__ == "__main__":
    unittest.main()
