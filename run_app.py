import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def npm_command():
    return "npm.cmd" if os.name == "nt" else "npm"


processes = []

try:
    processes = [
        subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "main.py")],
            cwd=ROOT_DIR,
        ),
        subprocess.Popen(
            [npm_command(), "--prefix", str(ROOT_DIR / "frontend"), "run", "dev"],
            cwd=ROOT_DIR,
        ),
    ]

    print("Backend: http://127.0.0.1:5000")
    print("Frontend: http://127.0.0.1:5173")
    print("Press Ctrl+C to stop both servers.")

    while True:
        for process in processes:
            if process.poll() is not None:
                raise SystemExit(process.returncode or 0)
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\nStopping servers...")
finally:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
