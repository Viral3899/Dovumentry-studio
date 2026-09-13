import logging
import traceback
import sqlite3
from pathlib import Path
from flask import has_request_context, request

from ..utils.paths import ERROR_LOG_PATH, AUTH_DB_PATH
from .auth import mysql_configured, mysql_connection


logger = logging.getLogger("documentary_studio")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(ERROR_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    terminal_handler = logging.StreamHandler()
    terminal_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(terminal_handler)


def record_error(error: Exception) -> None:
    error_type = type(error).__name__
    message = str(error) or error_type
    path = request.path if has_request_context() else "startup"
    method = request.method if has_request_context() else "SYSTEM"
    trace = traceback.format_exc()
    logger.error("%s %s %s: %s", method, path, error_type, message)
    try:
        if mysql_configured():
            with mysql_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO error_logs (error_type, message, path, method, traceback_text) VALUES (%s, %s, %s, %s, %s)",
                        (error_type, message, path, method, trace),
                    )
        else:
            with sqlite3.connect(AUTH_DB_PATH) as connection:
                connection.execute(
                    "INSERT INTO error_logs (error_type, message, path, method, traceback_text) VALUES (?, ?, ?, ?, ?)",
                    (error_type, message, path, method, trace),
                )
    except Exception as logging_error:
        logger.error("Could not persist error log: %s", logging_error)