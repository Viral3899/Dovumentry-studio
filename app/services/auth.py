import os
import sqlite3
from pathlib import Path

try:
    import pymysql
except Exception:
    pymysql = None

from werkzeug.security import check_password_hash, generate_password_hash

from ..utils.paths import AUTH_DB_PATH
from ..utils.constants import (
    DEMO_USERNAME, DEMO_EMAIL, DEMO_PHONE, DEMO_PASSWORD,
    DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD_HASH,
    DEFAULT_USER_USERNAME,
)


def mysql_configured() -> bool:
    return bool(os.getenv("MYSQL_HOST"))


def mysql_connection():
    if pymysql is None:
        raise RuntimeError("PyMySQL is required when MYSQL_HOST is configured.")
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "documentary_studio"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def configured_accounts():
    accounts = []
    if os.getenv("VERCEL") != "1":
        accounts.append((
            DEMO_USERNAME, DEMO_EMAIL, DEMO_PHONE, "admin",
            generate_password_hash(DEMO_PASSWORD)
        ))
    configured = [
        (os.getenv("ADMIN_USERNAME"), "admin", os.getenv("ADMIN_PASSWORD_HASH") or os.getenv("ADMIN_PASSWORD")),
        (os.getenv("USER_USERNAME"), "user", os.getenv("USER_PASSWORD_HASH") or os.getenv("USER_PASSWORD")),
    ]
    for username, role, password_value in configured:
        if username and password_value:
            password_hash = password_value if "$" in password_value else generate_password_hash(password_value)
            accounts.append((username.strip(), None, None, role, password_hash))
    if os.getenv("VERCEL") == "1" and not accounts:
        accounts.append((DEFAULT_ADMIN_USERNAME, None, None, "admin", DEFAULT_ADMIN_PASSWORD_HASH))
    return accounts


def initialize_auth_db() -> None:
    if mysql_configured():
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGINT PRIMARY KEY AUTO_INCREMENT,
                        username VARCHAR(120) NULL,
                        email VARCHAR(255) NULL,
                        phone VARCHAR(40) NULL,
                        role VARCHAR(20) NOT NULL,
                        password_hash TEXT NOT NULL,
                        UNIQUE KEY users_username_role (username, role),
                        UNIQUE KEY users_email_role (email, role),
                        UNIQUE KEY users_phone_role (phone, role)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS error_logs (
                        id BIGINT PRIMARY KEY AUTO_INCREMENT,
                        error_type VARCHAR(120) NOT NULL,
                        message TEXT NOT NULL,
                        path VARCHAR(500) NOT NULL,
                        method VARCHAR(20) NOT NULL,
                        traceback_text LONGTEXT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.executemany(
                    "INSERT IGNORE INTO users (username, email, phone, role, password_hash) VALUES (%s, %s, %s, %s, %s)",
                    configured_accounts(),
                )
                if os.getenv("VERCEL") != "1":
                    cursor.execute(
                        "UPDATE users SET email = %s, phone = %s WHERE username = %s AND role = 'admin'",
                        (DEMO_EMAIL, DEMO_PHONE, DEMO_USERNAME),
                    )
        return

    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(AUTH_DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                email TEXT,
                phone TEXT,
                role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                password_hash TEXT NOT NULL,
                UNIQUE (username, role)
            )
            """
        )
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        for column in ("email", "phone"):
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                traceback_text TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executemany(
            "INSERT OR IGNORE INTO users (username, email, phone, role, password_hash) VALUES (?, ?, ?, ?, ?)",
            configured_accounts(),
        )
        if os.getenv("VERCEL") != "1":
            connection.execute(
                "UPDATE users SET email = ?, phone = ? WHERE username = ? AND role = 'admin'",
                (DEMO_EMAIL, DEMO_PHONE, DEMO_USERNAME),
            )


def find_user(username: str, role: str):
    if mysql_configured():
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT username, email, phone, role, password_hash FROM users WHERE role = %s AND (username = %s OR email = %s OR phone = %s)",
                    (role, username, username.lower(), username),
                )
                return cursor.fetchone()
    with sqlite3.connect(AUTH_DB_PATH) as connection:
        return connection.execute(
            "SELECT username, email, phone, role, password_hash FROM users WHERE role = ? AND (username = ? OR email = ? OR phone = ?)",
            (role, username, username.lower(), username),
        ).fetchone()


def authentication_configured() -> bool:
    if mysql_configured():
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users LIMIT 1")
                has_users = cursor.fetchone() is not None
    else:
        with sqlite3.connect(AUTH_DB_PATH) as connection:
            has_users = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
    return has_users or google_auth_configured() or os.getenv("VERCEL") == "1"


def google_auth_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and (os.getenv("GOOGLE_ADMIN_EMAIL") or os.getenv("GOOGLE_USER_EMAIL")))


def set_authenticated_user(username: str, role: str, email: str = None, session=None) -> None:
    if session is None:
        from flask import session as flask_session
        session = flask_session
    session.clear()
    session["authenticated"] = True
    session["username"] = username
    session["role"] = role
    if email:
        session["email"] = email