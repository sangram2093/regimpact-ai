"""Run the same quality gates locally as CI. Uses this interpreter's environment."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("npm is required.")
    checks = [
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--config",
                "backend/pyproject.toml",
                "backend",
                "scripts",
                "data/public/fetch_sources.py",
            ],
            ROOT,
        ),
        ([sys.executable, "-m", "pytest", "backend/tests", "-q"], ROOT),
        ([sys.executable, "scripts/export_contracts.py", "--check"], ROOT),
        ([npm, "run", "lint"], ROOT / "frontend"),
        ([npm, "run", "typecheck"], ROOT / "frontend"),
        ([npm, "run", "test", "--", "--run"], ROOT / "frontend"),
        ([npm, "run", "build"], ROOT / "frontend"),
        ([sys.executable, "scripts/scan_secrets.py"], ROOT),
    ]
    for command, directory in checks:
        print(f"Running: {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=directory, check=False)
        if result.returncode:
            return result.returncode
    print("All local quality gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
