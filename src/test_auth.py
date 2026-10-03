import copy
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module
import auth


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = auth.DATABASE_PATH
        auth.DATABASE_PATH = Path(self.temporary_directory.name) / "users.sqlite3"
        self.original_activities = copy.deepcopy(app_module.activities)
        self.environment = patch.dict(
            os.environ,
            {
                "INITIAL_ADMIN_EMAIL": "staff@mergington.edu",
                "INITIAL_ADMIN_PASSWORD": "staff-password-long",
                "COOKIE_SECURE": "false",
            },
        )
        self.environment.start()
        self.client_context = TestClient(app_module.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        app_module.activities.clear()
        app_module.activities.update(self.original_activities)
        auth.DATABASE_PATH = self.original_database_path
        self.environment.stop()
        self.temporary_directory.cleanup()

    def register_student(self, email="student@mergington.edu"):
        return self.client.post(
            "/auth/register",
            json={"email": email, "password": "student-password-long"},
        )

    def test_protected_actions_reject_unauthenticated_requests(self):
        signup = self.client.post("/activities/Chess%20Club/signup")
        unregister = self.client.delete("/activities/Chess%20Club/unregister")
        self.assertEqual(signup.status_code, 401)
        self.assertEqual(unregister.status_code, 401)

    def test_student_actions_use_session_identity_not_query_email(self):
        response = self.register_student()
        self.assertEqual(response.status_code, 201)

        signup = self.client.post(
            "/activities/Chess%20Club/signup?email=another@mergington.edu"
        )
        self.assertEqual(signup.status_code, 200)
        self.assertIn(
            "student@mergington.edu",
            app_module.activities["Chess Club"]["participants"],
        )
        self.assertNotIn(
            "another@mergington.edu",
            app_module.activities["Chess Club"]["participants"],
        )

        unregister = self.client.delete(
            "/activities/Chess%20Club/unregister?email=another@mergington.edu"
        )
        self.assertEqual(unregister.status_code, 200)
        self.assertNotIn(
            "student@mergington.edu",
            app_module.activities["Chess Club"]["participants"],
        )
        self.assertIn(
            "michael@mergington.edu",
            app_module.activities["Chess Club"]["participants"],
        )

    def test_staff_cannot_use_student_activity_actions(self):
        response = self.client.post(
            "/auth/login",
            json={
                "email": "staff@mergington.edu",
                "password": "staff-password-long",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.post("/activities/Chess%20Club/signup").status_code, 403
        )

    def test_password_is_hashed_and_logout_revokes_session(self):
        response = self.register_student()
        self.assertEqual(response.status_code, 201)
        set_cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", set_cookie)
        self.assertIn("samesite=strict", set_cookie)
        connection = sqlite3.connect(auth.DATABASE_PATH)
        try:
            stored_hash = connection.execute(
                "SELECT password_hash FROM users WHERE email = ?",
                ("student@mergington.edu",),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertNotEqual(stored_hash, "student-password-long")
        self.assertEqual(stat.S_IMODE(auth.DATABASE_PATH.stat().st_mode), 0o600)

        self.assertEqual(self.client.get("/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_duplicate_registration_and_invalid_login_are_rejected(self):
        self.assertEqual(self.register_student().status_code, 201)
        duplicate = self.client.post(
            "/auth/register",
            json={"email": "STUDENT@MERGINGTON.EDU", "password": "another-long-password"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.client.post("/auth/logout")

        invalid_login = self.client.post(
            "/auth/login",
            json={"email": "student@mergington.edu", "password": "wrong-password-long"},
        )
        self.assertEqual(invalid_login.status_code, 401)


if __name__ == "__main__":
    unittest.main()
