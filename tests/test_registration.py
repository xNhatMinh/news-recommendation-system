import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

# Import the router without requiring a configured or reachable MySQL server.
with patch.dict(os.environ, {
    "MYSQL_USER": "test",
    "MYSQL_PASSWORD": "test",
    "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306",
    "MYSQL_DATABASE": "test",
}):
    from src.api.routes import auth


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    email VARCHAR(254) UNIQUE,
                    password_hash VARCHAR(255)
                )
            """))

        engine_patch = patch.object(auth, "engine", self.engine)
        engine_patch.start()
        self.addCleanup(engine_patch.stop)

        app = FastAPI()
        app.include_router(auth.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_registration_commits_hash_and_returns_public_fields(self):
        response = self.client.post("/auth/register", json={
            "email": "reader@example.com",
            "password": "a-long-password",
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {
            "user_id": 1,
            "email": "reader@example.com",
            "message": "Registration successful",
        })
        with self.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM users")).mappings().one()
        self.assertTrue(row["username"].startswith("user_"))
        self.assertLessEqual(len(row["username"]), 100)
        self.assertTrue(row["password_hash"].startswith("$argon2id$"))
        self.assertLessEqual(len(row["password_hash"]), 255)
        self.assertTrue(auth.password_hash.verify("a-long-password", row["password_hash"]))
        self.assertFalse(auth.password_hash.verify("wrong-password", row["password_hash"]))
        self.assertNotIn("a-long-password", response.text)
        self.assertNotIn(row["password_hash"], response.text)

    def test_each_account_has_a_different_salt(self):
        for email in ["first@example.com", "second@example.com"]:
            response = self.client.post("/auth/register", json={
                "email": email,
                "password": "same-password",
            })
            self.assertEqual(response.status_code, 201)
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT username, password_hash FROM users")).all()
        self.assertNotEqual(rows[0].username, rows[1].username)
        self.assertNotEqual(rows[0].password_hash, rows[1].password_hash)

    def test_invalid_input_does_not_write_to_database(self):
        long_email = "a" * 64 + "@" + ".".join(["b" * 63, "c" * 63, "d" * 60]) + ".com"
        invalid_inputs = [
            {"email": "invalid", "password": "12345678"},
            {"email": "reader@example.com", "password": "1234567"},
            {"email": "reader@example.com"},
            {"password": "12345678"},
            {"email": long_email, "password": "12345678"},
        ]
        for payload in invalid_inputs:
            with self.subTest(payload=payload):
                response = self.client.post("/auth/register", json=payload)
                self.assertEqual(response.status_code, 422)
        with self.engine.connect() as connection:
            count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        self.assertEqual(count, 0)

    def test_mysql_duplicate_email_returns_conflict(self):
        error = IntegrityError(
            "INSERT INTO users ...", {},
            MySQLIntegrityError(1062, "Duplicate entry for key 'users.uq_users_email'"),
        )
        with patch.object(self.engine, "begin", side_effect=error):
            response = self.client.post("/auth/register", json={
                "email": "reader@example.com",
                "password": "12345678",
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "Email already registered"})

    def test_other_integrity_errors_are_not_reported_as_duplicate_email(self):
        errors = [
            MySQLIntegrityError(1048, "Column cannot be null"),
            MySQLIntegrityError(1062, "Duplicate entry for key 'users.username'"),
        ]
        for original in errors:
            with self.subTest(code=original.args[0]):
                error = IntegrityError("INSERT INTO users ...", {}, original)
                with patch.object(self.engine, "begin", side_effect=error):
                    with self.assertRaises(IntegrityError):
                        self.client.post("/auth/register", json={
                            "email": "reader@example.com",
                            "password": "12345678",
                        })


if __name__ == "__main__":
    unittest.main()
