import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


def npm_command():
    return "npm.cmd" if os.name == "nt" else "npm"


try:
    if not (FRONTEND_DIR / "node_modules" / "vite").exists():
        subprocess.run(
            [npm_command(), "ci", "--prefix", str(FRONTEND_DIR)],
            cwd=ROOT_DIR,
            check=True,
        )

    build = subprocess.run(
        [npm_command(), "--prefix", str(FRONTEND_DIR), "run", "build"],
        cwd=ROOT_DIR,
        check=True,
    )
    if os.getenv("VERCEL") == "1":
        sys.exit(0)

    print("Documentary Studio: http://127.0.0.1:5000")
    print("Press Ctrl+C to stop the server.")
    subprocess.run([sys.executable, str(ROOT_DIR / "main.py")], cwd=ROOT_DIR, check=False)
except KeyboardInterrupt:
    print("\nStopping server...")
