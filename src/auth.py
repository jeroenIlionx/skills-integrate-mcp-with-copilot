import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

DATABASE_PATH = Path(
    os.getenv("AUTH_DATABASE_PATH", Path(__file__).with_name("users.sqlite3"))
)
SESSION_COOKIE = "mergington_session"
SESSION_LIFETIME_SECONDS = 8 * 60 * 60
PASSWORD_ITERATIONS = 600_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/auth", tags=["authentication"])


def secure_cookie_enabled() -> bool:
    value = os.getenv("COOKIE_SECURE", "true").lower()
    if value not in {"true", "false"}:
        raise RuntimeError("COOKIE_SECURE must be either 'true' or 'false'")
    return value == "true"


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    return normalized


@contextmanager
def database_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"{PASSWORD_ITERATIONS}${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        iterations, salt_hex, expected_hash = stored_hash.split("$")
        if int(iterations) != PASSWORD_ITERATIONS:
            return False
        salt = bytes.fromhex(salt_hex)
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_hash, expected_hash)


def initialize_auth_database() -> None:
    admin_email = os.getenv("INITIAL_ADMIN_EMAIL")
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        raise RuntimeError(
            "Set INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD before starting the app"
        )
    if len(admin_password) < 12:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 12 characters long")
    normalized_admin_email = normalize_email(admin_email)
    admin_password_hash = hash_password(admin_password)

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student', 'staff'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO users (email, password_hash, role)
            VALUES (?, ?, 'staff')
            ON CONFLICT(email) DO UPDATE SET
                password_hash = excluded.password_hash,
                role = 'staff'
            """,
            (normalized_admin_email, admin_password_hash),
        )
    os.chmod(DATABASE_PATH, 0o600)


def create_session(user_id: int, request: Request, response: Response) -> None:
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        revoke_session(old_token)

    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_LIFETIME_SECONDS
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with database_connection() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=secure_cookie_enabled(),
        samesite="strict",
        path="/",
    )


def revoke_session(token: str) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with database_connection() as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def get_current_user(request: Request) -> sqlite3.Row:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with database_connection() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.email, users.role, sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is not None and row["expires_at"] <= int(time.time()):
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
            )
            row = None

    if row is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return row


def get_current_student(
    user: sqlite3.Row = Depends(get_current_user),
) -> sqlite3.Row:
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    return user


@router.post("/register", status_code=201)
def register(
    credentials: Credentials,
    request: Request,
    response: Response,
) -> dict[str, str]:
    email = normalize_email(credentials.email)
    password_hash = hash_password(credentials.password)
    try:
        with database_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'student')",
                (email, password_hash),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        if "users.email" not in str(error):
            raise
        raise HTTPException(
            status_code=409, detail="An account already exists for this email"
        ) from error

    create_session(user_id, request, response)
    return {"email": email, "role": "student"}


@router.post("/login")
def login(
    credentials: Credentials,
    request: Request,
    response: Response,
) -> dict[str, str]:
    email = normalize_email(credentials.email)
    with database_connection() as connection:
        user = connection.execute(
            "SELECT id, email, password_hash, role FROM users WHERE email = ?", (email,)
        ).fetchone()
    if user is None or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    create_session(user["id"], request, response)
    return {"email": user["email"], "role": user["role"]}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        revoke_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return {"message": "Signed out"}


@router.get("/me")
def current_user(user: sqlite3.Row = Depends(get_current_user)) -> dict[str, str]:
    return {"email": user["email"], "role": user["role"]}
