"""Run the local API and Vite UI together without provisioning cloud resources."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_port(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise SystemExit(
                f"Port {port} is already in use. Stop your previous local server first."
            ) from exc


def stop_owned_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("Node.js/npm is required. See README.md for setup.")
    if not (ROOT / "frontend" / "node_modules").is_dir():
        raise SystemExit("Run npm ci --prefix frontend first.")
    for port in (8000, 5173):
        check_port(port)
    env = os.environ.copy()
    env.setdefault("REGIMPACT_MODE", "local")
    commands = [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "backend",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            ROOT,
        ),
        (
            [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
            ROOT / "frontend",
        ),
    ]
    processes: list[subprocess.Popen] = []
    try:
        for command, directory in commands:
            processes.append(subprocess.Popen(command, cwd=directory, env=env))
        print("RegImpact AI: http://127.0.0.1:5173", flush=True)
        print(
            "API docs: http://127.0.0.1:8000/docs - Ctrl+C stops both servers.",
            flush=True,
        )
        while all(process.poll() is None for process in processes):
            time.sleep(0.4)
        return next(
            (process.returncode for process in processes if process.returncode), 0
        )
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            stop_owned_process(process)


if __name__ == "__main__":
    sys.exit(main())
