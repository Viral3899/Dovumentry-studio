import os
from pathlib import Path
import sqlite3
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
RUNTIME_DIR = (
    Path(os.getenv("TMPDIR") or os.getenv("TEMP") or "/tmp") / "documentary-studio"
) if os.getenv("VERCEL") == "1" else BASE_DIR
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR = RUNTIME_DIR / "generated_sessions"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR = RUNTIME_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
BGM_DIR = BASE_DIR / "BGM"
AUTH_DB_PATH = Path(os.getenv("AUTH_DB_PATH", BASE_DIR / "auth.db"))
ERROR_LOG_PATH = RUNTIME_DIR / "errors.log"