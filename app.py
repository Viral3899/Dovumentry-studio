import json
import logging
import math
import os
import random
import re
import shutil
import sqlite3
import subprocess
import time
import traceback
import uuid
import wave
from datetime import datetime
from pathlib import Path
import sqlite3

from flask import Flask, has_request_context, jsonify, render_template, request, send_file, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except Exception:  # pragma: no cover
    Image = ImageDraw = ImageFont = ImageFilter = None

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env") if "BASE_DIR" in globals() else None
except Exception:
    pass

try:
    import pymysql
except Exception:  # pragma: no cover
    pymysql = None

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover
    genai = None
    types = None

try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
except Exception:  # pragma: no cover
    id_token = None
    google_requests = None

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
RUNTIME_DIR = (Path(os.getenv("TMPDIR") or os.getenv("TEMP") or "/tmp") / "documentary-studio") if os.getenv("VERCEL") == "1" else BASE_DIR
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR = RUNTIME_DIR / "generated_sessions"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR = RUNTIME_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
BGM_DIR = BASE_DIR / "BGM"
BGM_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
BGM_VOLUME = 0.20
NARRATION_VOLUME = 1.5
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD_HASH = "scrypt:32768:8:1$FeBqzBye8K9e0x1l$3584c102b33a948cc4c124fd615576388e9a3fb41dd414e81e2377ea82eb062a2fa57962867ceed0495f3e07aaba92f32e723a7625462008dad627e29e63922f"
DEFAULT_USER_USERNAME = "user"
AUTH_DB_PATH = Path(os.getenv("AUTH_DB_PATH", BASE_DIR / "auth.db"))
ERROR_LOG_PATH = RUNTIME_DIR / "errors.log"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"
DEMO_EMAIL = "demo@example.com"
DEMO_PHONE = "+10000000000"
VISUAL_STYLES = {
    "photorealistic": "Photorealistic cinematic documentary, premium film quality, realistic lighting, realistic people, accurate environment, natural colors, cinematic depth of field",
    "cartoon": "Stylized 2D cartoon animation, expressive clean shapes, rich colors, cinematic composition, appealing character design, storybook realism",
    "anime": "Cinematic anime illustration, detailed backgrounds, expressive characters, dramatic composition, polished hand-drawn visual language",
    "3d_animation": "High-quality 3D animated film style, detailed digital environments, expressive characters, cinematic lighting, polished render",
    "illustrated": "Rich editorial illustration, hand-painted textures, detailed composition, atmospheric colors, historically respectful visual storytelling",
    "archival": "Authentic archival documentary aesthetic, period-accurate film grain, muted colors, natural light, analog texture, respectful historical detail",
    "watercolor": "Detailed watercolor and ink illustration, visible paper texture, layered washes, delicate linework, expressive but accurate documentary composition",
    "graphic_novel": "Cinematic graphic novel art, bold ink contours, selective color, dramatic panels, textured shading, expressive visual storytelling",
    "claymation": "Handcrafted clay animation style, tactile sculpted surfaces, soft studio lighting, miniature sets, charming cinematic composition",
    "noir": "Atmospheric documentary noir, high-contrast light and shadow, restrained color palette, moody composition, realistic environments, cinematic tension",
}
SCRIPT_LANGUAGES = {
    "hindi": "natural Hindi written in Devanagari",
    "english": "natural English",
    "hinglish": "natural Hinglish using Hindi and English in Roman script",
    "bengali": "natural Bengali written in Bengali script",
    "tamil": "natural Tamil written in Tamil script",
    "telugu": "natural Telugu written in Telugu script",
    "marathi": "natural Marathi written in Devanagari",
    "gujarati": "natural Gujarati written in Gujarati script",
    "kannada": "natural Kannada written in Kannada script",
    "malayalam": "natural Malayalam written in Malayalam script",
    "punjabi": "natural Punjabi written in Gurmukhi script",
}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "local-development-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("VERCEL", "").lower() == "1",
)


# Serve the Vite production build from the same Flask origin.
# The previous build was successful, but Flask had no `/` route, so the
# browser received a 404 which the error handler exposed as HTTP 500.
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
    # Never swallow API routes. Unknown API paths should remain API 404s.
    if path.startswith("api/"):
        return jsonify({"success": False, "message": "API route not found."}), 404
    requested = FRONTEND_DIST / path
    if requested.is_file():
        return send_from_directory(FRONTEND_DIST, path)
    # React Router/client-side routes fall back to index.html.
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return jsonify({"success": False, "message": "Frontend build not found. Run: npm run build"}), 503

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


def mysql_configured():
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
        accounts.append((DEMO_USERNAME, DEMO_EMAIL, DEMO_PHONE, "admin", generate_password_hash(DEMO_PASSWORD)))
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


def initialize_auth_db():
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


def find_user(username, role):
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


def record_error(error):
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


initialize_auth_db()


def authentication_configured():
    if mysql_configured():
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users LIMIT 1")
                has_users = cursor.fetchone() is not None
    else:
        with sqlite3.connect(AUTH_DB_PATH) as connection:
            has_users = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
    return has_users or google_auth_configured() or os.getenv("VERCEL") == "1"


def google_auth_configured():
    return bool(os.getenv("GOOGLE_CLIENT_ID") and (os.getenv("GOOGLE_ADMIN_EMAIL") or os.getenv("GOOGLE_USER_EMAIL")))


def set_authenticated_user(username, role, email=None):
    session.clear()
    session["authenticated"] = True
    session["username"] = username
    session["role"] = role
    if email:
        session["email"] = email


@app.before_request
def require_admin_authentication():
    if not request.path.startswith("/api/") or request.path in {"/api/auth/login", "/api/auth/google", "/api/auth/me"}:
        return None
    if not authentication_configured():
        return None
    if session.get("authenticated"):
        return None
    return jsonify({"success": False, "message": "Admin authentication is required.", "authenticated": False}), 401


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    record_error(error)
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "An internal error occurred. Check the server log."}), 500
    return "An internal error occurred. Check the server log.", 500


@app.route("/api/auth/login", methods=["POST"])
def admin_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("identifier") or payload.get("username") or "").strip()
    password = payload.get("password") or ""
    requested_role = (payload.get("role") or "admin").strip().lower()
    if requested_role not in {"admin", "user"}:
        return jsonify({"success": False, "message": "Choose a valid account type."}), 400
    if not authentication_configured():
        return jsonify({"success": False, "message": "Authentication is not configured."}), 503
    account = find_user(username, requested_role)
    if not account:
        return jsonify({"success": False, "message": f"Invalid {requested_role} credentials."}), 401
    configured_username = account["username"] if isinstance(account, dict) else account[0]
    role = account["role"] if isinstance(account, dict) else account[3]
    password_hash = account["password_hash"] if isinstance(account, dict) else account[4]
    try:
        valid = check_password_hash(password_hash, password)
    except ValueError:
        valid = False
    if not valid:
        return jsonify({"success": False, "message": f"Invalid {requested_role} credentials."}), 401
    set_authenticated_user(configured_username, role)
    return jsonify({"success": True, "username": configured_username, "role": role})


@app.route("/api/auth/google", methods=["POST"])
def google_login():
    credential = (request.get_json(silent=True) or {}).get("credential")
    if not credential or not google_auth_configured() or id_token is None:
        return jsonify({"success": False, "message": "Google sign-in is not configured."}), 503
    try:
        claims = id_token.verify_oauth2_token(credential, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID"))
    except Exception:
        return jsonify({"success": False, "message": "Google sign-in could not be verified."}), 401
    email = (claims.get("email") or "").strip().lower()
    if not claims.get("email_verified"):
        return jsonify({"success": False, "message": "Use a verified Google email address."}), 401
    admin_email = os.getenv("GOOGLE_ADMIN_EMAIL", "").strip().lower()
    user_email = os.getenv("GOOGLE_USER_EMAIL", "").strip().lower()
    if email == admin_email:
        role = "admin"
    elif email == user_email:
        role = "user"
    else:
        return jsonify({"success": False, "message": "This Google account is not allowed."}), 403
    set_authenticated_user(claims.get("name") or email, role, email)
    return jsonify({"success": True, "username": claims.get("name") or email, "email": email, "role": role})


@app.route("/api/auth/me")
def admin_me():
    authenticated = bool(session.get("authenticated"))
    return jsonify({
        "success": True,
        "authenticated": authenticated or not authentication_configured(),
        "username": session.get("username") if authenticated else (os.getenv("ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME) if not authentication_configured() else None),
        "role": session.get("role") if authenticated else ("admin" if not authentication_configured() else None),
        "email": session.get("email") if authenticated else None,
        "auth_configured": authentication_configured(),
        "google_configured": google_auth_configured(),
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID") if google_auth_configured() else None,
    })


@app.route("/api/auth/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return jsonify({"success": True})


def slugify(value: str) -> str:
    value = (value or "untitled").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def log_event(session_dir: Path, message: str):
    log_path = session_dir / "generation_log.txt"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_timestamp()}] {message}\n")


def write_state(session_dir: Path, data: dict):
    state_path = session_dir / "session_state.json"
    state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_state(session_dir: Path):
    state_path = session_dir / "session_state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


API_KEYS_FILE = RUNTIME_DIR / "api_keys.json"

def _load_saved_api_keys():
    try:
        return json.loads(API_KEYS_FILE.read_text(encoding="utf-8")) if API_KEYS_FILE.exists() else {}
    except Exception:
        return {}

def _get_api_key(provider):
    env = "GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY"
    return (os.getenv(env) or _load_saved_api_keys().get(provider) or "").strip()

def _save_api_key(provider, key):
    if provider not in {"groq", "gemini"} or len(key.strip()) < 10: raise ValueError("Enter a valid Groq or Gemini API key.")
    data=_load_saved_api_keys(); data[provider]=key.strip(); API_KEYS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.environ["GROQ_API_KEY" if provider=="groq" else "GEMINI_API_KEY"] = key.strip()

def provider_status():
    saved=_load_saved_api_keys(); return {"groq":bool(os.getenv("GROQ_API_KEY") or saved.get("groq")),"gemini":bool(os.getenv("GEMINI_API_KEY") or saved.get("gemini"))}

def is_resource_exhausted(exc):
    msg=str(exc).lower(); status=getattr(exc,"status_code",None) or getattr(exc,"code",None)
    return status==429 or any(x in msg for x in ("rate limit","quota","resource exhausted","too many requests","limit exceeded","capacity","429","exhausted"))

def is_auth_error(exc):
    msg=str(exc).lower(); status=getattr(exc,"status_code",None) or getattr(exc,"code",None)
    return status in {401,403} or any(x in msg for x in ("invalid api key","authentication","unauthorized","api key not valid","permission denied","forbidden"))

class ProviderRequiredError(RuntimeError):
    def __init__(self, provider, reason, alternate=None, detail=""):
        super().__init__(reason); self.provider=provider; self.reason=reason; self.alternate=alternate; self.detail=detail

def provider_required_response(exc):
    labels={"groq":"Groq","gemini":"Gemini"}
    purpose = getattr(exc, "purpose", "")
    return jsonify({"success":False,"provider_required":True,"provider":exc.provider,"alternate_provider":exc.alternate,"resource_exhausted":is_resource_exhausted(exc.detail),"purpose":purpose,"allow_default_voice": purpose == "audio","message":f"{labels[exc.provider]} API key is required. {exc.reason}"+(f"\n\nProvider error: {exc.detail}" if exc.detail else "")}),409

def get_groq_client():
    key=_get_api_key("groq")
    if not key or Groq is None: return None
    return Groq(api_key=key)

def get_gemini_client():
    key=_get_api_key("gemini")
    if not key or genai is None: return None
    try: return genai.Client(api_key=key)
    except Exception: return None

def call_text_provider(prompt, system_prompt, session_dir=None, purpose="text", groq_kwargs=None):
    """Use Groq first, but do not mistake model/empty responses for bad API keys.

    Authentication failures require a new Groq key. Quota/capacity exhaustion falls
    through to Gemini. Empty responses are retried briefly, then fall through to
    Gemini when available. This prevents repeated, misleading API-key prompts.
    """
    groq = get_groq_client()
    if groq is None:
        exc = ProviderRequiredError("groq", "Groq API key is required for this step. Enter and save your Groq API key.", "gemini")
        exc.purpose = purpose
        raise exc

    kwargs = dict(groq_kwargs or {})
    kwargs.setdefault("model", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
    kwargs.setdefault("messages", [{"role":"system","content":system_prompt},{"role":"user","content":prompt}])

    last_groq_error = None
    for attempt in range(1, 3):
        try:
            r = groq.chat.completions.create(**kwargs)
            text = (r.choices[0].message.content or "").strip()
            if text:
                return text, "groq"
            last_groq_error = RuntimeError("Groq returned an empty response. The selected Groq model did not return usable text.")
            if session_dir:
                log_event(session_dir, f"Groq {purpose} empty response (attempt {attempt}/2)")
            if attempt < 2:
                time.sleep(1.0)
                continue
            break
        except Exception as ge:
            last_groq_error = ge
            if session_dir:
                log_event(session_dir, f"Groq {purpose} failed (attempt {attempt}/2): {ge}")
            if is_auth_error(ge):
                exc = ProviderRequiredError("groq", "Groq authentication failed. Re-enter or replace the Groq API key, then retry.", "gemini", str(ge))
                exc.purpose = purpose
                raise exc
            if is_resource_exhausted(ge):
                break
            if attempt < 2:
                time.sleep(1.0)
                continue
            # A non-auth model/server failure should not trigger an API-key dialog.
            break

    # Groq was unavailable after retrying. Prefer a saved Gemini key for text work.
    gemini = get_gemini_client()
    if gemini is not None:
        try:
            r = gemini.models.generate_content(
                model=os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash"),
                contents=f"{system_prompt}\n\n{prompt}",
            )
            text = (getattr(r, "text", "") or "").strip()
            if text:
                if session_dir:
                    log_event(session_dir, f"{purpose} completed with Gemini fallback after Groq unavailable")
                return text, "gemini"
            raise RuntimeError("Gemini returned an empty response")
        except Exception as ee:
            if session_dir:
                log_event(session_dir, f"Gemini fallback for {purpose} failed: {ee}")
            # Only ask for Gemini when Groq could not be used and Gemini itself is unavailable.
            if is_auth_error(ee) or is_resource_exhausted(ee):
                exc = ProviderRequiredError("gemini", "Gemini is unavailable. Enter or replace the Gemini API key to continue.", "gemini", str(ee))
                exc.purpose = purpose
                raise exc
            raise RuntimeError(f"AI generation failed after Groq retry and Gemini fallback: {ee}") from ee

    # No Gemini key is available. If Groq was exhausted/failed, ask only for the
    # alternate key; do not repeatedly ask for the same Groq key.
    detail = str(last_groq_error or "Groq did not return usable text.")
    exc = ProviderRequiredError(
        "gemini",
        "Groq is temporarily unavailable. Enter a Gemini API key to continue with the alternate provider.",
        "gemini",
        detail,
    )
    exc.purpose = purpose
    raise exc


def get_session_dir(session_id: str) -> Path:
    generated_dir = GENERATED_DIR / session_id
    if generated_dir.exists():
        return generated_dir
    return PROJECTS_DIR / session_id


def topic_folder_name(value: str) -> str:
    name = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return name[:80] or "documentary"


def topic_filename(session_id: str, suffix: str) -> str:
    """Build a topic-named filename, e.g. topic_filename('my_topic', '_script.txt') -> 'my_topic_script.txt'."""
    return f"{session_id}{suffix}"


def read_session_script(session_dir: Path, state: dict, session_id: str = "") -> str:
    names = []
    if state.get("script_filename"):
        names.append(state["script_filename"])
    if session_id:
        names.append(topic_filename(session_id, "_script.txt"))
    names.append("documentary_script.txt")
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        path = session_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8")
    return (state.get("script") or "").strip()


def get_duration(filename: str) -> float:
    if not Path(filename).exists():
        return 0.0
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            filename,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        return 0.0
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def count_required_images(audio_duration: float, image_seconds: float = 5, transition_seconds: float = 0) -> int:
    """Calculate image count from the actual narration duration. One image represents 5 seconds.
    The final image may be shorter than 5 seconds when the audio duration is not an exact multiple.
    """
    if audio_duration <= 0:
        return 1
    return max(1, math.ceil(float(audio_duration) / float(image_seconds)))


def render_count(payload, name, default=12, minimum=1, maximum=120):
    try:
        value = int(payload.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number.")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def split_script_for_segments(script: str, count: int):
    """Split narration into exactly count natural-ish spoken segments."""
    text = re.sub(r"\s+", " ", (script or "").strip())
    if count <= 1:
        return [text]
    sentences = [x.strip() for x in re.split(r"(?<=[.!?।॥])\s+", text) if x.strip()]
    if len(sentences) < count:
        words = text.split()
        size = max(1, math.ceil(len(words) / count))
        segments = [" ".join(words[i:i + size]).strip() for i in range(0, len(words), size)]
    else:
        segments = []
        total = len(sentences)
        start = 0
        for i in range(count):
            remaining_groups = count - i
            remaining_sentences = total - start
            take = max(1, math.ceil(remaining_sentences / remaining_groups))
            segments.append(" ".join(sentences[start:start + take]).strip())
            start += take
    # Guarantee exact count by merging extras or padding the last segment.
    while len(segments) > count:
        segments[-2] = (segments[-2] + " " + segments[-1]).strip()
        segments.pop()
    while len(segments) < count:
        segments.append(segments[-1] if segments else text)
    return segments[:count]


def concatenate_audio_files(audio_paths, output_path: Path):
    """Concatenate generated narration clips into one WAV without re-encoding when possible."""
    concat_file = output_path.with_suffix(".concat.txt")
    concat_file.write_text("\n".join(f"file '{str(path).replace(chr(39), chr(39)+chr(39))}'" for path in audio_paths), encoding="utf-8")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(output_path)],
        capture_output=True, text=True, check=False
    )
    concat_file.unlink(missing_ok=True)
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"Audio concatenation failed: {result.stderr}")
    return output_path


def render_setting(payload, name, default, minimum, maximum):
    try:
        value = float(payload.get(name, default))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def make_silence_wav(path: Path, duration_seconds: float):
    sample_rate = 22050
    frames = []
    for _ in range(int(duration_seconds * sample_rate)):
        frames.append(0)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join((int(value)).to_bytes(2, byteorder="little", signed=True) for value in frames))


def make_placeholder_audio(path: Path, text: str, voice_name: str):
    length = max(30, len(text.split()) * 0.45)
    sample_rate = 22050
    total_frames = int(length * sample_rate)
    audio = bytearray()
    for idx in range(total_frames):
        phase = (idx / sample_rate) * 2 * math.pi * 180
        tone = math.sin(phase) * 6000 + math.sin(phase * 1.5) * 2000
        sample = int(max(-32768, min(32767, tone)))
        audio.extend(sample.to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio)
    return length


def generate_local_audio(path: Path, script: str, voice_name: str):
    """Generate spoken fallback audio using Microsoft Edge's free TTS service (cross-platform)."""
    import asyncio
    import edge_tts

    hindi_voices = {
        "male": "hi-IN-MadhurNeural",
        "female": "hi-IN-SwaraNeural",
    }
    voice = hindi_voices.get(voice_name.lower(), "hi-IN-SwaraNeural")

    mp3_path = path.with_suffix(".mp3")

    async def _synthesize():
        communicate = edge_tts.Communicate(script, voice)
        await communicate.save(str(mp3_path))

    asyncio.run(_synthesize())

    if not mp3_path.exists() or mp3_path.stat().st_size < 1000:
        raise RuntimeError("edge-tts produced no audio output")

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "22050", "-ac", "1", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    mp3_path.unlink(missing_ok=True)
    if result.returncode != 0 or not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")

    return path

def extract_tts_audio(response):
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline_data = getattr(part, "inline_data", None)
            data = getattr(inline_data, "data", None) if inline_data else None
            if isinstance(data, bytes):
                return data
    return None


def generate_real_audio(path: Path, script: str, voice_name: str):
    client = get_gemini_client()
    if client is None or types is None:
        raise ProviderRequiredError("gemini", "Gemini narration requires a Gemini API key.", "gemini")

    response = client.models.generate_content(
        model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
        contents=(
            "Read only the following documentary narration as natural spoken Hindi. "
            f"Use a serious documentary voice named {voice_name}.\n\n{script}"
        ),
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
        ),
    )
    audio_bytes = extract_tts_audio(response)
    if not audio_bytes:
        return None

    if audio_bytes[:4] == b"RIFF":
        path.write_bytes(audio_bytes)
    else:
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(audio_bytes)
    return path


def build_fallback_script(topic: str, genre: str) -> str:
    return (
        f"भारत की विविध धरती और उसकी जीवंत स्मृतियों के बीच {topic} की कहानी धीरे-धीरे हमारे सामने खुलती है। "
        f"यह केवल एक घटना या स्थान की कहानी नहीं, बल्कि उन लोगों, विचारों और परिस्थितियों का सफर है जिन्होंने इसे आकार दिया। "
        f"समय के साथ बदलते समाज, स्थानीय परंपराएं, कारीगरों की मेहनत और आम लोगों की उम्मीदें इस कथा को अपना मानवीय स्वर देती हैं। "
        f"इस विषय को समझने के लिए हमें उसके इतिहास, भूगोल और सांस्कृतिक संदर्भ को साथ देखना होगा। "
        f"कभी किसी नदी के किनारे बसे नगरों ने व्यापार और ज्ञान को आगे बढ़ाया, तो कभी गांवों और कस्बों में पीढ़ियों से चली आ रही कला ने पहचान बनाई। "
        f"उपलब्ध प्रमाण हमें कई महत्वपूर्ण संकेत देते हैं, लेकिन हर ऐतिहासिक कहानी की तरह यहां भी कुछ प्रश्न और अनिश्चितताएं बाकी हैं। "
        f"इन्हीं प्रमाणों, अनुभवों और बदलते समय के बीच {topic} का अर्थ और गहरा होता जाता है। "
        f"आज जब हम पीछे मुड़कर देखते हैं, तो यह कहानी हमें बताती है कि भारत की पहचान केवल उसके स्मारकों या घटनाओं में नहीं, बल्कि उन लोगों की मेहनत, स्मृति और साझा संस्कृति में भी बसती है। "
        f"और शायद यही कारण है कि {topic} आज भी हमारे लिए महत्वपूर्ण है।"
    )


def is_hindi_script(text: str) -> bool:
    devanagari = len(re.findall(r"[\u0900-\u097F]", text or ""))
    letters = len(re.findall(r"[A-Za-z\u0900-\u097F]", text or ""))
    return devanagari >= 20 and devanagari / max(letters, 1) >= 0.35


def has_excessive_word_repetition(text: str, max_repeats: int = 3) -> bool:
    """Flag scripts where a content word (4+ chars) recurs too often, a sign of generic/templated text."""
    words = re.findall(r"[\w\u0900-\u097F]{4,}", (text or "").lower())
    if len(words) < 20:
        return False
    counts = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    most_common = max(counts.values()) if counts else 0
    return most_common > max_repeats


def generate_script_with_backend(topic, genre, session_id, script_language="hindi", target_duration=60):
    sd=get_session_dir(session_id); lang=SCRIPT_LANGUAGES.get(script_language,SCRIPT_LANGUAGES["hindi"]); minimum=max(40,math.ceil(target_duration*2.0)); target=max(minimum,math.ceil(target_duration*2.2)); maximum=max(target+20,math.ceil(target_duration*2.6))
    prompt=(f"Write a complete cinematic {lang} {genre or 'documentary'} narration about {topic}. Requested length {target_duration:.0f} seconds. Write {target} words, never fewer than {minimum} or more than {maximum}. Start with a topic-specific viral hook and curiosity gap; give context; tell the story chronologically; build to the key revelation; explain consequences; end smoothly with a memorable thought. No headings, bullets, scene labels, production notes or generic filler. Never invent facts. Return only narration.\n\nTOPIC: {topic}")
    for attempt in range(3):
        text,provider=call_text_provider(prompt+(f"\nRetry {attempt+1}: ensure at least {minimum} words." if attempt else ""),f"You are a professional {lang} documentary writer.",sd,"script",{"temperature":0.8,"max_tokens":max(1800,min(6000,math.ceil(target_duration*5)))})
        if len(re.findall(r"\S+",text))>=minimum and (script_language!="hindi" or is_hindi_script(text)): log_event(sd,f"Script generated with {provider}"); return text
    raise RuntimeError("AI returned a script shorter than the requested duration.")


@app.route("/api/providers/status")
def api_provider_status():
    return jsonify({"success": True, "providers": provider_status(), "required_primary": "groq", "alternate": "gemini"})

@app.route("/api/providers/key", methods=["POST"])
def api_provider_key():
    payload = request.get_json(silent=True) or {}
    provider = str(payload.get("provider") or "").lower().strip()
    key = str(payload.get("api_key") or "").strip()
    try:
        _save_api_key(provider, key)
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "provider": provider, "providers": provider_status(), "message": f"{provider.title()} API key saved for future use."})

@app.route("/api/create-session", methods=["POST"])
def create_session():
    payload = request.get_json(silent=True) or {}
    topic = (payload.get("topic") or "").strip()
    genre = (payload.get("genre") or "documentary").strip()
    visual_style = (payload.get("visual_style") or "photorealistic").strip()
    script_language = (payload.get("script_language") or "hindi").strip()
    if not topic:
        return jsonify({"success": False, "message": "Topic is required."}), 400
    if visual_style not in VISUAL_STYLES:
        return jsonify({"success": False, "message": "Unsupported visual style."}), 400
    if script_language not in SCRIPT_LANGUAGES:
        return jsonify({"success": False, "message": "Unsupported script language."}), 400

    try:
        target_duration = render_setting(payload, "target_duration", 60, 20, 600)
        image_seconds = 5.0
        transition_seconds = render_setting(payload, "transition_seconds", 1, 0, 4.9)
        narration_volume = render_setting(payload, "narration_volume", NARRATION_VOLUME, 0, 3)
        bgm_volume = render_setting(payload, "bgm_volume", BGM_VOLUME, 0, 1)
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    if transition_seconds >= image_seconds:
        return jsonify({"success": False, "message": "transition_seconds must be less than image_seconds."}), 400

    session_id = topic_folder_name(topic)
    session_dir = PROJECTS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "images").mkdir(exist_ok=True)
    (session_dir / "topic.txt").write_text(topic, encoding="utf-8")
    log_path = session_dir / "generation_log.txt"
    log_path.write_text("", encoding="utf-8")
    log_event(session_dir, f"Session created for topic: {topic} | genre: {genre}")

    state = {
        "session_id": session_id,
        "topic": topic,
        "genre": genre,
        "visual_style": visual_style,
        "script_language": script_language,
        "folder": str(session_dir),
        "status": "created",
        "script": "",
        "prompts": [],
        "audio_file": "",
        "audio_duration": 0.0,
        "video_file": "",
        "music_file": "",
        "validated_images": {},
        "image_seconds": image_seconds,
        "transition_seconds": transition_seconds,
        "narration_volume": narration_volume,
        "bgm_volume": bgm_volume,
        "target_duration": target_duration,
        "media_count": max(1, math.ceil(target_duration / 5.0)),
        "audio_segment_count": 1,
        "image_prompt_count": max(1, math.ceil(target_duration / 5.0)),
        "required_image_count": max(1, math.ceil(target_duration / 5.0)),
    }
    write_state(session_dir, state)
    return jsonify({"success": True, "session_id": session_id, "folder": str(session_dir), "topic": topic, "genre": genre,
                    "target_duration": target_duration, "required_image_count": max(1, math.ceil(target_duration / 5.0)), "audio_clip_count": 1})


@app.route("/api/session/<session_id>/download/<path:filename>")
def download_file(session_id, filename):
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404
    target = (session_dir / filename).resolve()
    try:
        return send_file(target, as_attachment=True)
    except Exception:
        return jsonify({"success": False, "message": "File not found."}), 404


@app.route("/api/generate-script", methods=["POST"])
def generate_script_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    topic = state.get("topic") or payload.get("topic") or ""
    genre = state.get("genre") or payload.get("genre") or "documentary"

    try:
        target_duration = render_setting(
            payload,
            "target_duration",
            state.get("target_duration", 60),
            20,
            600,
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    state["target_duration"] = target_duration
    try:
        script = generate_script_with_backend(topic, genre, session_id, state.get("script_language", "hindi"), target_duration)
    except ProviderRequiredError as exc:
        return provider_required_response(exc)
    script_filename = topic_filename(session_id, "_script.txt")
    script_path = session_dir / script_filename
    script_path.write_text(script, encoding="utf-8")
    legacy_script_path = session_dir / "documentary_script.txt"
    if legacy_script_path.exists() and legacy_script_path != script_path:
        legacy_script_path.unlink()

    state["status"] = "script_ready"
    state["script"] = script
    state["script_filename"] = script_filename
    write_state(session_dir, state)
    log_event(session_dir, f"Script generated for topic: {topic} | genre: {genre}")
    return jsonify({"success": True, "script": script, "download_url": f"/api/session/{session_id}/download/{script_filename}"})


@app.route("/api/update-script", methods=["POST"])
def update_script_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    script = (payload.get("script") or "").strip()
    if not session_id or not script:
        return jsonify({"success": False, "message": "session_id and script are required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    script_filename = state.get("script_filename") or topic_filename(session_id, "_script.txt")
    (session_dir / script_filename).write_text(script, encoding="utf-8")
    state["script"] = script
    state["script_filename"] = script_filename
    state["status"] = "script_edited"
    write_state(session_dir, state)
    log_event(session_dir, "Documentary script edited and saved from the frontend")
    return jsonify({
        "success": True,
        "script": script,
        "download_url": f"/api/session/{session_id}/download/{script_filename}",
    })


@app.route("/api/generate-audio", methods=["POST"])
def generate_audio_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    voice = (payload.get("voice") or "Iapetus").strip() or "Iapetus"
    use_default_voice = bool(payload.get("use_default_voice"))
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    script = read_session_script(session_dir, state, session_id)
    if not script:
        return jsonify({"success": False, "message": "Script must be generated before audio."}), 400

    # Narration is generated as one continuous script. TTS may be split internally
    # into provider-safe chunks, but the user never chooses an audio/image count.
    tts_chunks = []
    normalized = re.sub(r"\s+", " ", script).strip()
    sentences = [x.strip() for x in re.split(r"(?<=[.!?।॥])\s+", normalized) if x.strip()]
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > 3500:
            tts_chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        tts_chunks.append(current.strip())
    if not tts_chunks:
        tts_chunks = [normalized]

    segment_dir = session_dir / "audio_segments"
    segment_dir.mkdir(exist_ok=True)
    for old in segment_dir.glob("*.wav"):
        old.unlink(missing_ok=True)

    segment_paths = []
    try:
        for index, segment in enumerate(tts_chunks, start=1):
            segment_path = segment_dir / f"{index}.wav"
            generated_audio = None
            try:
                if use_default_voice:
                    generated_audio = generate_local_audio(segment_path, segment, "female")
                else:
                    generated_audio = generate_real_audio(segment_path, segment, voice)
            except ProviderRequiredError as exc:
                exc.detail = str(exc.detail or exc.reason)
                return jsonify({
                    "success": False,
                    "provider_required": True,
                    "provider": "gemini",
                    "alternate_provider": "default_voice",
                    "allow_default_voice": True,
                    "purpose": "audio",
                    "message": "Gemini narration is unavailable. Enter/save a Gemini API key, or choose Use Default Voice to continue without Gemini." + (f"\n\nProvider error: {exc.detail}" if exc.detail else ""),
                }), 409
            except Exception as exc:
                if is_resource_exhausted(exc) or is_auth_error(exc):
                    return jsonify({
                        "success": False,
                        "provider_required": True,
                        "provider": "gemini",
                        "alternate_provider": "default_voice",
                        "allow_default_voice": True,
                        "purpose": "audio",
                        "message": "Gemini narration is unavailable. Enter/save a Gemini API key, or choose Use Default Voice to continue without Gemini.\n\nProvider error: " + str(exc),
                    }), 409
                # A transient Gemini/TTS response failure should not become a key dialog.
                raise
            duration = get_duration(str(segment_path)) if generated_audio else 0.0
            if not segment_path.exists() or duration <= 0:
                raise RuntimeError(f"Could not generate narration audio chunk {index}.")
            segment_paths.append(segment_path)

        audio_filename = topic_filename(session_id, "_narration.wav")
        audio_path = session_dir / audio_filename
        audio_path.unlink(missing_ok=True)
        concatenate_audio_files(segment_paths, audio_path)
    except Exception as exc:
        log_event(session_dir, f"Narration generation failed: {exc}")
        return jsonify({"success": False, "message": str(exc)}), 503

    audio_duration = get_duration(str(audio_path))
    image_seconds = 5.0
    required_image_count = max(1, math.ceil(float(state.get("target_duration") or audio_duration) / image_seconds))
    state["status"] = "audio_ready"
    state["audio_file"] = str(audio_path)
    state["audio_filename"] = audio_filename
    state["audio_duration"] = round(float(audio_duration), 2)
    state["voice"] = "Default Voice" if use_default_voice else voice
    state["audio_provider"] = "default_voice" if use_default_voice else "gemini"
    # One final narration clip is exposed to the user; provider-safe chunks are internal.
    state["audio_segment_count"] = 1
    state["audio_segments"] = [str(audio_path)]
    state["media_count"] = required_image_count
    state["required_image_count"] = required_image_count
    state["image_prompt_count"] = required_image_count
    write_state(session_dir, state)
    log_event(session_dir, f"Narration generated from full script; duration={state['audio_duration']}s; required images={required_image_count} at 5s/image")
    return jsonify({
        "success": True,
        "voice": voice,
        "segment_count": 1,
        "duration": round(float(audio_duration), 2),
        "image_count": required_image_count,
        "audio_clip_count": 1,
        "audio_url": f"/api/session/{session_id}/download/{audio_filename}",
        "download_url": f"/api/session/{session_id}/download/{audio_filename}",
    })


def parse_prompts(text):
    matches=re.findall(r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s*|\Z)",text or "",flags=re.MULTILINE|re.DOTALL)
    return [x.strip() for _,x in matches if x.strip()] or [x.strip() for x in (text or "").splitlines() if x.strip()]


def image_index_from_filename(filename: str):
    """Read a leading image number from generated or user-uploaded names."""
    stem = Path(filename).stem
    match = re.match(r"^\s*(\d+)(?:\D|$)", stem)
    return int(match.group(1)) if match else 0


def enforce_visual_style(prompts, visual_style):
    return "\n\n".join(f"{i}. {p} MANDATORY VISUAL STYLE: {VISUAL_STYLES.get(visual_style,VISUAL_STYLES['photorealistic'])}." for i,p in enumerate(prompts,1))

def generate_prompt_text(topic, script, count, visual_style="photorealistic"):
    """Generate exactly `count` prompts without relying on one huge LLM response.

    Groq sometimes stops early when a large prompt batch approaches the model's
    output-token limit. Generate small internal batches, then renumber them into
    one continuous list. There is intentionally no user-facing 24-image limit.
    """
    style = VISUAL_STYLES.get(visual_style, VISUAL_STYLES["photorealistic"])
    batch_size = 6
    all_prompts = []

    for batch_start in range(1, count + 1, batch_size):
        batch_end = min(count, batch_start + batch_size - 1)
        batch_count = batch_end - batch_start + 1

        # Give each batch a proportional narration slice so visual chronology
        # stays aligned from the first image through the last image.
        words = script.split()
        total_words = len(words)
        start_word = round((batch_start - 1) * total_words / count)
        end_word = round(batch_end * total_words / count)
        script_chunk = " ".join(words[start_word:end_word]).strip() or script

        prompt = f"""Generate EXACTLY {batch_count} numbered cinematic documentary image prompts.

IMAGE NUMBERS MUST BE {batch_start} THROUGH {batch_end}.
Do not stop early. Do not omit any number. Do not add extra numbers.

TOPIC:
{topic}

NARRATION SEGMENT:
{script_chunk}

Each prompt is one self-contained scene in chronological order. Include:
- subject
- setting and historical/time context
- action
- lighting
- mood/atmosphere
- camera angle/composition

VISUAL STYLE:
{style}

16:9 landscape. Photorealistic cinematic documentary. Realistic people and environments.
No text, subtitles, captions, logos, watermarks or UI. Maintain recurring-character consistency.
Do not invent facts, names, dates, places or events not supported by the narration.

OUTPUT FORMAT — RETURN ONLY THESE NUMBERED PROMPTS:
{batch_start}. prompt
{batch_start + 1}. prompt
...
{batch_end}. prompt
"""

        last_error = None
        parsed = []
        for attempt in range(1, 4):
            raw, _ = call_text_provider(
                prompt,
                "You create concise, factual cinematic documentary image prompts. Always complete every requested numbered item.",
                purpose=f"image prompts {batch_start}-{batch_end}",
                groq_kwargs={"temperature": 0.4, "max_tokens": 3200},
            )
            parsed = parse_prompts(raw)
            if len(parsed) == batch_count:
                break
            last_error = f"Expected {batch_count} prompts for batch {batch_start}-{batch_end}, got {len(parsed)}."

            # Explicitly ask the provider to repair a short batch instead of
            # failing the entire documentary after one truncated response.
            prompt += f"\n\nIMPORTANT RETRY: Your previous response contained {len(parsed)} prompts. Return ALL {batch_count} prompts, numbered {batch_start} through {batch_end}."

        if len(parsed) != batch_count:
            raise RuntimeError(last_error or f"Expected {batch_count} prompts for batch {batch_start}-{batch_end}.")

        all_prompts.extend(parsed)

    if len(all_prompts) != count:
        raise RuntimeError(f"Expected {count} image prompts, got {len(all_prompts)}.")

    return enforce_visual_style(all_prompts, visual_style)

def generate_generation_prompt_text(topic,prompts,visual_style="photorealistic"):
    return "IMAGE GENERATION INSTRUCTIONS\nGenerate images in chronological order. Keep recurring characters and visual continuity consistent. Export as 1.jpeg, 2.jpeg, 3.jpeg...\n\n"+"\n\n".join(prompts)

@app.route("/api/generate-prompts", methods=["POST"])
def generate_prompts_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    script = read_session_script(session_dir, state, session_id)
    if not script:
        return jsonify({"success": False, "message": "Script is missing."}), 400

    audio_filename = state.get("audio_filename") or topic_filename(session_id, "_narration.wav")
    audio_duration = float(state.get("audio_duration") or get_duration(str(session_dir / audio_filename)) or 0.0)
    audio_duration = float(state.get("audio_duration") or 0.0)
    image_seconds = 5.0
    required_count = int(state.get("required_image_count") or max(1, math.ceil(float(state.get("target_duration") or audio_duration) / image_seconds)))
    if required_count < 1 or required_count > 240:
        return jsonify({"success": False, "message": "The calculated image count is outside the supported range (1-240)."}), 400
    visual_style = (payload.get("visual_style") or state.get("visual_style") or "photorealistic").strip()
    if visual_style not in VISUAL_STYLES:
        return jsonify({"success": False, "message": "Unsupported visual style."}), 400
    state["visual_style"] = visual_style
    try:
        prompt_text = generate_prompt_text(state.get("topic") or "documentary subject", script, required_count, visual_style)
    except ProviderRequiredError as exc:
        return provider_required_response(exc)
    prompts_filename = topic_filename(session_id, "_image_prompts.txt")
    prompt_file = session_dir / prompts_filename
    prompt_file.write_text(prompt_text, encoding="utf-8")

    prompts = parse_prompts(prompt_text)
    state["status"] = "prompts_ready"
    state["prompts"] = prompts
    state["prompts_filename"] = prompts_filename
    state["required_prompt_count"] = len(prompts)
    state["required_image_count"] = len(prompts)
    state["media_count"] = len(prompts)
    generation_prompt_text = generate_generation_prompt_text(state.get("topic") or "documentary subject", prompts, visual_style)
    generation_prompts_filename = topic_filename(session_id, "_image_generation_prompts.txt")
    generation_prompt_file = session_dir / generation_prompts_filename
    generation_prompt_file.write_text(generation_prompt_text, encoding="utf-8")
    state["generation_prompt_file"] = str(generation_prompt_file)
    state["generation_prompts_filename"] = generation_prompts_filename
    write_state(session_dir, state)
    log_event(session_dir, f"Image prompts generated: {len(prompts)} prompts saved in session folder")
    return jsonify({
        "success": True,
        "prompts": prompts,
        "generation_prompts": generation_prompt_text,
        "download_url": f"/api/session/{session_id}/download/{prompts_filename}",
        "generation_download_url": f"/api/session/{session_id}/download/{generation_prompts_filename}",
    })


@app.route("/api/session/<session_id>/download-images")
def download_images_zip(session_id):
    session_dir = get_session_dir(session_id)
    image_dir = session_dir / "images"
    if not image_dir.exists():
        return jsonify({"success": False, "message": "No image folder found for this project."}), 404

    image_files = [
        path for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.isdigit()
    ]
    image_files.sort(key=lambda path: int(path.stem))
    if not image_files:
        return jsonify({"success": False, "message": "No numbered images are available yet."}), 404

    archive_base = session_dir / f"{session_id}_numbered_images"
    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=image_dir)
    return send_file(archive_path, as_attachment=True, download_name=f"{session_id}_numbered_images.zip")


@app.route("/api/upload-images", methods=["POST"])
def upload_images_route():
    session_id = request.form.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    prompts = state.get("prompts")
    if not prompts:
        prompts_filename = state.get("prompts_filename") or topic_filename(session_id, "_image_prompts.txt")
        prompts_path = session_dir / prompts_filename
        prompts = parse_prompts(prompts_path.read_text(encoding="utf-8")) if prompts_path.exists() else []
    if not prompts:
        return jsonify({"success": False, "message": "Generate prompts before uploading images."}), 400

    image_dir = session_dir / "images"
    image_dir.mkdir(exist_ok=True)
    uploaded_files = request.files.getlist("files")
    results = []

    for index, uploaded_file in enumerate(uploaded_files, start=1):
        if not uploaded_file or uploaded_file.filename == "":
            continue

        original_name = secure_filename(uploaded_file.filename)
        extension = Path(original_name).suffix.lower() or ".jpg"
        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            results.append({"name": original_name, "status": "rejected", "reason": "Unsupported file type."})
            log_event(session_dir, f"Image upload rejected: {original_name} | unsupported file type")
            continue

        expected_index = image_index_from_filename(original_name)
        if not expected_index or expected_index > len(prompts):
            expected_index = index if index <= len(prompts) else len(prompts)

        candidate_path = image_dir / f"{expected_index}{extension}"
        uploaded_file.save(candidate_path)
        matched_prompt = prompts[expected_index - 1] if expected_index - 1 < len(prompts) else ""
        expected_prompt_preview = matched_prompt[:80]
        results.append({
            "name": original_name,
            "status": "accepted",
            "target": f"{expected_index}{extension}",
            "expected_prompt": expected_prompt_preview,
        })
        state.setdefault("validated_images", {})[str(expected_index)] = str(candidate_path)
        log_event(session_dir, f"Image validation passed: {candidate_path.name} matched prompt {expected_index}")

    state["status"] = "images_validated" if results else "images_pending"
    write_state(session_dir, state)
    uploaded_count = len({
        int(Path(path).stem)
        for path in image_dir.iterdir()
        if path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.isdigit()
    })
    missing_numbers = [number for number in range(1, len(prompts) + 1) if not (image_dir / f"{number}.jpg").exists() and not any((image_dir / f"{number}{extension}").exists() for extension in IMAGE_EXTENSIONS - {".jpg"})]
    return jsonify({
        "success": True,
        "results": results,
        "required_count": len(prompts),
        "uploaded_count": uploaded_count,
        "missing_numbers": missing_numbers,
    })


def build_video_pipeline(image_files, audio_path, output_video,
                          image_seconds=5, transition_seconds=1,
                          narration_volume=NARRATION_VOLUME, bgm_volume=BGM_VOLUME):
    """
    Single-pass pipeline: images + narration + background music -> final video.
    Mirrors documentary_pipeline_2.py's create_video(), but parameterized for
    per-session settings instead of global constants. Replaces the old
    build_video_command() + separate finalize-music second pass.
    """
    audio_duration = get_duration(str(audio_path))
    if audio_duration <= 0:
        raise RuntimeError("Narration audio has no readable duration.")

    image_count = len(image_files)
    image_duration = (
        audio_duration + (image_count - 1) * transition_seconds
    ) / image_count

    # Pick background music.
    music_files = [
        path for path in BGM_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in BGM_EXTENSIONS
    ] if BGM_DIR.exists() else []
    if not music_files:
        raise RuntimeError(f"No background music files found in {BGM_DIR}.")
    selected_bgm = random.choice(music_files)

    # NVENC detection with CPU fallback.
    encoder_check = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
    )
    use_nvenc = "h264_nvenc" in encoder_check.stdout

    if use_nvenc:
        video_codec = [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-rc", "vbr",
            "-cq", "20",
            "-b:v", "8M",
            "-maxrate", "12M",
            "-bufsize", "16M",
        ]
    else:
        video_codec = [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
        ]

    cmd = ["ffmpeg", "-y"]

    # IMAGE INPUTS
    for image_path in image_files:
        cmd += [
            "-loop", "1",
            "-t", f"{image_duration:.3f}",
            "-i", str(image_path),
        ]

    # AUDIO INPUTS
    cmd += ["-i", str(audio_path)]
    cmd += ["-stream_loop", "-1", "-i", str(selected_bgm)]

    filters = []
    for index in range(image_count):
        filters.append(
            f"[{index}:v]setpts=PTS-STARTPTS,"
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            "zoompan=z='min(zoom+0.0007,1.08)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={round(image_duration * 30)}:s=1920x1080:fps=30,"
            "trim=duration=" + f"{image_duration:.3f}" + ","
            "setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
            f"[v{index}]"
        )

    current = "v0"
    offset = image_duration - transition_seconds
    for index in range(1, image_count):
        next_video = f"x{index}"
        filters.append(
            f"[{current}][v{index}]xfade=transition=fade:"
            f"duration={transition_seconds}:offset={offset:.3f},"
            "format=yuv420p"
            f"[{next_video}]"
        )
        current = next_video
        offset += image_duration - transition_seconds

    narration_input = image_count
    music_input = image_count + 1
    filters.extend([
        f"[{narration_input}:a]volume={narration_volume}[narration]",
        f"[{music_input}:a]volume={bgm_volume}[music]",
        "[narration][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
    ])

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]",
        "-map", "[aout]",
        "-t", f"{audio_duration:.3f}",
        *video_codec,
        "-c:a", "aac",
        "-b:a", "192k",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_video),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "Video assembly failed.")

    produced_duration = get_duration(str(output_video))
    if abs(produced_duration - audio_duration) > 0.15:
        raise RuntimeError(
            f"Final A/V duration mismatch: audio={audio_duration:.3f}s, "
            f"video={produced_duration:.3f}s"
        )

    return output_video, audio_duration, produced_duration, selected_bgm.name


@app.route("/api/build-video", methods=["POST"])
def build_video_route():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    image_dir = session_dir / "images"
    files = sorted(
        [path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda path: int(path.stem) if path.stem.isdigit() else 999,
    )
    if not files:
        return jsonify({"success": False, "message": "Upload images before building the video."}), 400

    state = load_state(session_dir)
    try:
        image_seconds = 5.0
        transition_seconds = render_setting(payload, "transition_seconds", state.get("transition_seconds", 1), 0, 4.9)
        narration_volume = render_setting(payload, "narration_volume", state.get("narration_volume", NARRATION_VOLUME), 0, 3)
        bgm_volume = render_setting(payload, "bgm_volume", state.get("bgm_volume", BGM_VOLUME), 0, 1)
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    if transition_seconds >= image_seconds:
        return jsonify({"success": False, "message": "transition_seconds must be less than image_seconds."}), 400

    audio_filename = state.get("audio_filename") or topic_filename(session_id, "_narration.wav")
    audio_path = session_dir / audio_filename
    if not audio_path.exists():
        return jsonify({"success": False, "message": "Generate narration audio before building the video."}), 400
    audio_duration = get_duration(str(audio_path))
    required_count = len(state.get("prompts") or []) or count_required_images(audio_duration, 5, 0)
    expected_numbers = set(range(1, required_count + 1))
    actual_numbers = {int(path.stem) for path in files if path.stem.isdigit()}
    missing_numbers = sorted(expected_numbers - actual_numbers)
    if required_count and missing_numbers:
        return jsonify({
            "success": False,
            "message": f"Missing images: {', '.join(map(str, missing_numbers))}.",
            "required_count": required_count,
            "uploaded_count": len(actual_numbers),
            "missing_numbers": missing_numbers,
        }), 400

    video_filename = topic_filename(session_id, ".mp4")
    output_video = session_dir / video_filename

    try:
        _, audio_duration, produced_duration, music_track = build_video_pipeline(
            files, audio_path, output_video,
            image_seconds, transition_seconds, narration_volume, bgm_volume,
        )
    except RuntimeError as error:
        return jsonify({"success": False, "message": str(error)}), 500

    state["status"] = "finalized"
    state["video_file"] = str(output_video)
    state["video_filename"] = video_filename
    state["music_file"] = str(output_video)
    state["image_seconds"] = image_seconds
    state["transition_seconds"] = transition_seconds
    state["narration_volume"] = narration_volume
    state["bgm_volume"] = bgm_volume
    write_state(session_dir, state)
    log_event(
        session_dir,
        f"Video pipeline complete: images+narration+music merged in one pass, saved as {video_filename} "
        f"(track={music_track}, audio={audio_duration:.3f}s, video={produced_duration:.3f}s)",
    )

    return jsonify({
        "success": True,
        "video_url": f"/api/session/{session_id}/download/{video_filename}",
        "download_url": f"/api/session/{session_id}/download/{video_filename}",
        "music_track": music_track,
        "filename": video_filename,
    })


def _strip_json_fences(text: str) -> str:
    text = (text or "").strip()
    if "```" not in text:
        return text
    for part in text.split("```"):
        part = part.strip()
        if part[:4].lower() == "json":
            part = part[4:].strip()
        if part.startswith(("[", "{")):
            return part
    return text


def _first_json_start(text: str):
    positions = [index for index in (text.find("["), text.find("{")) if index != -1]
    return min(positions) if positions else None


def _close_and_load(fragment: str):
    """Close unterminated strings/containers, then json.loads. Returns None on failure."""
    if not fragment:
        return None
    in_string = False
    escape_next = False
    stack = []
    repaired = []
    for ch in fragment:
        if escape_next:
            escape_next = False
            repaired.append(ch)
            continue
        if ch == "\\" and in_string:
            escape_next = True
            repaired.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch in ("{", "["):
                stack.append("}" if ch == "{" else "]")
            elif ch in ("}", "]") and stack and stack[-1] == ch:
                stack.pop()
        repaired.append(ch)
    if in_string:
        repaired.append('"')
    joined = "".join(repaired).rstrip()
    while joined.endswith(","):
        joined = joined[:-1].rstrip()
        # Drop a dangling incomplete key: {"a": 1, "wh
        if joined.endswith(":"):
            last_quote = joined.rfind('"')
            prev_comma = joined.rfind(",")
            cut = prev_comma if prev_comma > last_quote else joined.rfind("{")
            if cut != -1:
                joined = joined[:cut].rstrip()
    joined += "".join(reversed(stack))
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return None


def _extract_json(text):
    """Robustly extract and parse a JSON value (object or array) from model output."""
    if not text:
        return None
    text = _strip_json_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = _first_json_start(text)
    if start is None:
        return None
    fragment = text[start:]
    parsed = _close_and_load(fragment)
    if parsed is not None:
        return parsed
    # Walk back from the truncated tail until a prefix closes cleanly.
    trim_from = max(0, len(fragment) - 800)
    for end in range(len(fragment) - 1, trim_from, -1):
        parsed = _close_and_load(fragment[:end])
        if parsed is not None:
            return parsed
    return None


def _repair_truncated_array(text):
    """Recover complete JSON objects from truncated arrays or mixed prose, ignoring braces inside strings."""
    if not text:
        return []
    text = _strip_json_fences(text)
    items = []
    in_string = False
    escape_next = False
    depth = 0
    start = None
    for index, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = index
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:index + 1])
                    if isinstance(obj, dict):
                        items.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    if start is not None:
        repaired = _close_and_load(text[start:])
        if isinstance(repaired, dict) and repaired.get("topic"):
            items.append(repaired)
    return items


def _coerce_topic_list(parsed) -> list:
    if isinstance(parsed, dict):
        if isinstance(parsed.get("topics"), list):
            parsed = parsed["topics"]
        elif parsed.get("topic"):
            parsed = [parsed]
        else:
            parsed = []
    if not isinstance(parsed, list):
        return []
    topics = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = str(item.get("topic") or "").strip()
        if not title:
            continue
        keywords = item.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [part.strip() for part in re.split(r"[,;]", keywords) if part.strip()]
        elif not isinstance(keywords, list):
            keywords = []
        topics.append({
            "topic": title,
            "hook": str(item.get("hook") or "").strip(),
            "angle": str(item.get("angle") or "").strip(),
            "why": str(item.get("why") or "").strip(),
            "keywords": [str(keyword).strip() for keyword in keywords if str(keyword).strip()][:8],
        })
    return topics


def _topics_from_quoted_fields(text: str) -> list:
    titles = re.findall(r'"topic"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    hooks = re.findall(r'"hook"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    angles = re.findall(r'"angle"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    whys = re.findall(r'"why"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    topics = []
    for index, title in enumerate(titles):
        decoded = json.loads(f'"{title}"')
        if not decoded.strip():
            continue
        topics.append({
            "topic": decoded.strip(),
            "hook": json.loads(f'"{hooks[index]}"') if index < len(hooks) else "",
            "angle": json.loads(f'"{angles[index]}"') if index < len(angles) else "",
            "why": json.loads(f'"{whys[index]}"') if index < len(whys) else "",
            "keywords": [],
        })
    return topics


@app.route("/api/suggest-topics", methods=["POST"])
def suggest_topics_route():
    """Generate topic ideas with the same Groq→Gemini fallback as every text step."""
    payload = request.get_json(silent=True) or {}
    seed = (payload.get("seed") or "").strip()
    genre = (payload.get("genre") or "history").strip()
    language = (payload.get("language") or "hindi").strip()
    if not seed:
        return jsonify({"success": False, "message": "seed is required."}), 400

    prompt = (
        f"Turn this seed into 5 specific, researchable {genre} documentary topics.\n"
        f"SEED: {seed}\n"
        "Return ONLY a JSON object with this shape:\n"
        '{"topics":[{"topic":"...","hook":"...","angle":"...","why":"...","keywords":["..."]}]}\n'
        "Rules: exactly 5 items. topic is a title, not a question. hook/angle/why are each one short sentence. "
        "keywords is an array of 4 short strings. Keep every string under 22 words. "
        f"Write all text in {language}. No markdown."
    )
    session_dir = RUNTIME_DIR
    last_error = ""
    for attempt in range(1, 4):
        try:
            raw, provider = call_text_provider(
                prompt + f"\n\nAttempt {attempt}: return the complete object, not a truncated response.",
                'Return only valid JSON. Use the object {"topics":[...]} with no markdown. Complete all 5 items.',
                session_dir=session_dir,
                purpose="suggest-topics",
                groq_kwargs={"temperature": 0.3, "max_tokens": 2600},
            )
            topics = _coerce_topic_list(_extract_json(raw))
            if len(topics) < 1:
                topics = _coerce_topic_list(_repair_truncated_array(raw))
            if len(topics) < 1:
                topics = _topics_from_quoted_fields(raw)
            if topics:
                return jsonify({"success": True, "topics": topics[:5], "provider": provider})
            last_error = f"attempt {attempt}: model returned no parseable topics"
            log_event(session_dir, f"suggest-topics {last_error}")
        except ProviderRequiredError as exc:
            return provider_required_response(exc)
        except Exception as exc:
            last_error = str(exc)
            log_event(session_dir, f"suggest-topics attempt {attempt} failed: {exc}")
            if attempt < 3:
                time.sleep(1)

    return jsonify({"success": False, "message": f"Topic generation failed after {3} attempts: {last_error}"}), 503


def _find_font(language="en", bold=False):
    """Find a font that supports both Latin and Devanagari when Hindi is requested."""
    candidates = []
    if str(language).lower().startswith("hi"):
        candidates += [
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-CondensedBold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf",
            r"C:\Windows\Fonts\Nirmala.ttf" if not bold else r"C:\Windows\Fonts\NirmalaB.ttf",
            r"C:\Windows\Fonts\NirmalaUI.ttf" if not bold else r"C:\Windows\Fonts\NirmalaUI-Bold.ttf",
        ]
    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _fit_font(draw, text, max_width, start_size, language="en", bold=True):
    font_path = _find_font(language, bold=bold)
    size = start_size
    while size >= 22:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(font_path, 22) if font_path else ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = str(text or "").split()
    if not words:
        return ""
    lines, current = [], ""
    for word in words:
        trial = word if not current else current + " " + word
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def _make_thumbnail_image(session_dir, thumbnail_text, language="en"):
    """Create a finished 1280x720 thumbnail with the generated text baked into the image."""
    if Image is None:
        raise RuntimeError("Pillow is not installed; cannot render thumbnail text overlay.")

    width, height = 1280, 720
    images_dir = session_dir / "images"
    source = None
    for path in sorted(images_dir.glob("*")) if images_dir.exists() else []:
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            source = path
            break

    if source:
        try:
            base = Image.open(source).convert("RGB")
            base.thumbnail((width, height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (width, height), (12, 16, 20))
            canvas.paste(base, ((width-base.width)//2, (height-base.height)//2))
        except Exception:
            canvas = Image.new("RGB", (width, height), (12, 16, 20))
    else:
        # Useful fallback when the user has not uploaded image frames yet.
        canvas = Image.new("RGB", (width, height), (12, 16, 20))
        draw_bg = ImageDraw.Draw(canvas)
        for y in range(height):
            t = y / height
            draw_bg.line((0, y, width, y), fill=(int(12+18*t), int(18+22*t), int(28+45*t)))

    # Cinematic darkening so the overlay remains readable.
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, width, height), fill=(0, 0, 0, 55))
    od.rectangle((0, height*0.48, width, height), fill=(0, 0, 0, 125))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(canvas)
    main = str(thumbnail_text.get("main_title", "")).strip()
    subtitle = str(thumbnail_text.get("subtitle", "")).strip()
    label = str(thumbnail_text.get("label", "")).strip()
    margin = 62
    max_width = width - margin*2

    # Accent label / badge.
    y = height - 250
    if label:
        label_font = _fit_font(draw, label, 380, 26, language, True)
        lb = draw.textbbox((0, 0), label, font=label_font)
        lw, lh = lb[2]-lb[0], lb[3]-lb[1]
        draw.rounded_rectangle((margin, y, margin+lw+34, y+lh+22), radius=8, fill=(233,69,96,235))
        draw.text((margin+17, y+11), label, font=label_font, fill=(255,255,255,255))
        y += lh + 42

    main_font = _fit_font(draw, main, max_width, 76, language, True)
    main_wrapped = _wrap_text(draw, main, main_font, max_width)
    # subtle shadow + pale headline
    draw.multiline_text((margin+3, y+5), main_wrapped, font=main_font, fill=(0,0,0,180), spacing=4)
    draw.multiline_text((margin, y), main_wrapped, font=main_font, fill=(255,244,238,255), spacing=4)
    main_h = draw.multiline_textbbox((margin, y), main_wrapped, font=main_font, spacing=4)[3] - y
    y += main_h + 18

    if subtitle:
        sub_font = _fit_font(draw, subtitle, max_width, 34, language, True)
        sub_wrapped = _wrap_text(draw, subtitle, sub_font, max_width)
        draw.multiline_text((margin+2, y+3), sub_wrapped, font=sub_font, fill=(0,0,0,170), spacing=3)
        draw.multiline_text((margin, y), sub_wrapped, font=sub_font, fill=(246,192,64,255), spacing=3)

    # Small branding-free framing line.
    draw.line((margin, height-42, width-margin, height-42), fill=(255,255,255,80), width=2)

    out = session_dir / "thumbnail_with_text.png"
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out


@app.route("/api/generate-social", methods=["POST"])
def generate_social_route():
    """After the final video is ready, generate Instagram caption + YouTube title + description."""
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    if not session_id:
        return jsonify({"success": False, "message": "session_id is required."}), 400

    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404

    state = load_state(session_dir)
    topic = state.get("topic") or ""
    genre = state.get("genre") or "documentary"
    language = str(payload.get("language") or "en").lower()
    language_name = "Hindi (Devanagari)" if language.startswith("hi") else "English"

    full_script = read_session_script(session_dir, state, session_id).strip()
    script_snippet = full_script[:800]
    context_line = f"Script context (first 800 chars):\n{script_snippet}\n\n" if script_snippet else ""

    # Three small focused calls — one field each to guarantee completion.
    prompt_yt = (
        f"Documentary topic: {topic}\nGenre: {genre}\nOutput language: {language_name}\n\n"
        f"{context_line}"
        'Return a JSON object with exactly these two keys:\n'
        '"youtube_title": video title under 70 chars, factual and compelling\n'
        '"youtube_description": 80 words max. Hook first sentence. 2 context sentences. End with 4 hashtags.\n\n'
        "Start with { and end with }. No markdown."
    )
    prompt_thumb = (
        f"Documentary topic: {topic}\nGenre: {genre}\nOutput language: {language_name}\n\n"
        'Return a JSON object with exactly two keys:\n'
        '"thumbnail_prompt": one vivid sentence describing a cinematic 16:9 YouTube thumbnail image for this documentary. Bold dramatic lighting, high contrast, cinematic color grading, rule of thirds composition, no text in the image itself. Make it visually striking with strong visual hierarchy.\n'
        '"thumbnail_text": a JSON object with these sub-keys:\n'
        '  "main_title": 2-4 bold impactful words for the large headline text on the thumbnail (all caps, high contrast, readable at small sizes)\n'
        '  "subtitle": one short punchy line under the title, max 6 words, creates curiosity or urgency\n'
        '  "label": optional short badge text like "FULL DOCUMENTARY" or "UNTOLD HISTORY" or "SHOCKING TRUTH" (or empty string)\n\n'
        "Start with { and end with }. No markdown."
    )
    prompt_ig = (
        f"Documentary topic: {topic}\nGenre: {genre}\nOutput language: {language_name}\n\n"
        f"{context_line}"
        'Return JSON with exactly these keys: \"instagram_caption\" and \"tags\".\n'
        'instagram_caption: a strong hook, 2 short context sentences, and a CTA. Keep the caption under 500 characters and finish with 10 relevant hashtags.\n'
        'tags: JSON array of exactly 8 short YouTube SEO tags, without #.\n'
    )

    def call_model(prompt_text):
        return call_text_provider(prompt_text, "Return only valid JSON. Do not use markdown. Do not explain your answer.", session_dir=session_dir, purpose="social copy", groq_kwargs={"temperature":0.4,"max_tokens":1200})


    last_error = None
    social = {}

    for attempt in range(3):
        try:
            raw_yt, provider = call_model(prompt_yt)
            raw_thumb, _ = call_model(prompt_thumb)
            raw_ig, _ = call_model(prompt_ig)

            log_event(session_dir, f"social yt    (attempt {attempt+1}): {raw_yt[:120]}")
            log_event(session_dir, f"social thumb (attempt {attempt+1}): {raw_thumb[:120]}")
            log_event(session_dir, f"social ig    (attempt {attempt+1}): {raw_ig[:120]}")

            parsed_yt    = _extract_json(raw_yt)    or {}
            parsed_thumb = _extract_json(raw_thumb) or {}
            parsed_ig    = _extract_json(raw_ig)    or {}

            merged = {**parsed_yt, **parsed_thumb, **parsed_ig}

            if merged.get("youtube_title"):
                social = merged
                break

            last_error = f"attempt {attempt+1}: yt={raw_yt[:60]} | ig={raw_ig[:60]}"
            log_event(session_dir, f"social unparseable: {last_error}")
        except ProviderRequiredError as exc:
            return provider_required_response(exc)
        except Exception as exc:
            last_error = str(exc)
            log_event(session_dir, f"generate-social attempt {attempt+1} failed: {exc}")

    if not social:
        return jsonify({"success": False, "message": f"Social copy generation failed after 3 attempts. Last error: {last_error}"}), 500

    thumbnail_text = social.get("thumbnail_text") if isinstance(social.get("thumbnail_text"), dict) else {}
    tags = social.get("tags", []) if isinstance(social.get("tags"), list) else []
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    # Keep the response shape stable so the Social Director UI can render every tab
    # even when a model returns an incomplete field on one attempt.
    result = {
        "youtube_title": str(social.get("youtube_title", "")).strip(),
        "youtube_description": str(social.get("youtube_description", "")).strip(),
        "instagram_caption": str(social.get("instagram_caption", "")).strip(),
        "tags": tags[:20],
        "thumbnail_prompt": str(social.get("thumbnail_prompt", "")).strip(),
        "thumbnail_text": {
            "main_title": str(thumbnail_text.get("main_title", "")).strip(),
            "subtitle": str(thumbnail_text.get("subtitle", "")).strip(),
            "label": str(thumbnail_text.get("label", "")).strip(),
        },
    }
    # Render the thumbnail itself so the text is baked into the downloaded image.
    try:
        thumb_path = _make_thumbnail_image(session_dir, result["thumbnail_text"], language)
        result["thumbnail_image_url"] = f"/api/session/{session_id}/download/{thumb_path.name}"
    except Exception as exc:
        log_event(session_dir, f"thumbnail render failed: {exc}")
        result["thumbnail_image_url"] = ""
        result["thumbnail_image_error"] = str(exc)

    log_event(session_dir, f"Social media copy generated for: {topic} | language={language_name}")
    return jsonify({"success": True, **result})


@app.route("/api/session/<session_id>/state")
def get_session_state(session_id):
    session_dir = get_session_dir(session_id)
    if not session_dir.exists():
        return jsonify({"success": False, "message": "Session not found."}), 404
    state = load_state(session_dir)
    return jsonify({"success": True, "state": state})


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG") == "1",
        use_reloader=False,
        host="0.0.0.0",
        port=5000,
    )