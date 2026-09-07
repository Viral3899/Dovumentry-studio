import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def npm_command():
    return "npm.cmd" if os.name == "nt" else "npm"


try:
    build = subprocess.run(
        [npm_command(), "--prefix", str(ROOT_DIR / "frontend"), "run", "build"],
        cwd=ROOT_DIR,
        check=True,
    )
    print("Documentary Studio: http://127.0.0.1:5000")
    print("Press Ctrl+C to stop the server.")
    subprocess.run([sys.executable, str(ROOT_DIR / "main.py")], cwd=ROOT_DIR, check=False)
except KeyboardInterrupt:
    print("\nStopping server...")
