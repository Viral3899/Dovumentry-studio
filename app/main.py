import os
import logging
import traceback
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory, session, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import sqlite3

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except Exception:
    Image = ImageDraw = ImageFont = ImageFilter = None

# Import services
from app.services import (
    initialize_auth_db,
    authentication_configured,
    google_auth_configured,
    set_authenticated_user,
    record_error,
    provider_status,
)
from app.services.api_keys import provider_status as api_provider_status

# Import routes
from app.api.auth_routes import register_auth_routes
from app.api.provider_routes import register_provider_routes
from app.api.session_routes import register_session_routes

# Constants
from app.utils.constants import (
    VISUAL_STYLES, SCRIPT_LANGUAGES, IMAGE_EXTENSIONS,
    DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD_HASH,
    DEFAULT_USER_USERNAME, DEMO_USERNAME, DEMO_PASSWORD,
    DEMO_EMAIL, DEMO_PHONE, BGM_VOLUME, NARRATION_VOLUME
)
from app.utils.paths import BASE_DIR, FRONTEND_DIST, RUNTIME_DIR, GENERATED_DIR, PROJECTS_DIR, BGM_DIR, AUTH_DB_PATH, ERROR_LOG_PATH

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "local-development-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("VERCEL", "").lower() == "1",
)

# Serve frontend
@app.route("/", methods=["GET"])
def serve_frontend_index():
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return jsonify({
            "success": False,
            "message": "Frontend build not found. Run: npm run build"
        }), 503
    return send_from_directory(FRONTEND_DIST, "index.html")

@app.route("/favicon.ico", methods=["GET"])
def serve_favicon():
    favicon = BASE_DIR / "frontend" / "public" / "favicon.svg"
    if favicon.exists():
        return send_file(favicon, mimetype="image/svg+xml")
    return ("", 204)

@app.route("/<path:path>", methods=["GET"])
def serve_frontend_assets(path):
    if path.startswith("api/"):
        return jsonify({"success": False, "message": "API route not found."}), 404
    requested = FRONTEND_DIST / path
    if requested.is_file():
        return send_from_directory(FRONTEND_DIST, path)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return jsonify({"success": False, "message": "Frontend build not found. Run: npm run build"}), 503

# Initialize auth DB
initialize_auth_db()

# Register routes
register_auth_routes(app)
register_provider_routes(app)
register_session_routes(app)

# Global error handler
@app.errorhandler(Exception)
def handle_unexpected_error(error):
    record_error(error)
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "An internal error occurred. Check the server log."}), 500
    return "An internal error occurred. Check the server log.", 500

# Authentication middleware
@app.before_request
def require_admin_authentication():
    if not request.path.startswith("/api/") or request.path in {"/api/auth/login", "/api/auth/google", "/api/auth/me"}:
        return None
    if not authentication_configured():
        return None
    if session.get("authenticated"):
        return None
    return jsonify({"success": False, "message": "Admin authentication is required.", "authenticated": False}), 401
if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG") == "1",
        use_reloader=False,
        host="0.0.0.0",
        port=5000,
    )