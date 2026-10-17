"""Conservative local secret-pattern check; prints locations, never secret values.

This supplements, rather than replaces, a maintained release-time secret scanner.
Examines tracked and nonignored new files through Git.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "google-api-key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "github-token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "github-fine-grained-token": re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
    "service-account-private-key": re.compile(rb'"private_key"\s*:\s*"[^"\r\n]{30,}'),
}


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    findings: list[str] = []
    checked = 0
    for entry in sorted(set(result.stdout.split(b"\0"))):
        if not entry:
            continue
        relative = entry.decode("utf-8")
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 3_000_000:
            continue
        content = path.read_bytes()
        if b"\0" in content:
            continue
        checked += 1
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                line = content.count(b"\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: {name}")
    if findings:
        print("Potential secrets require review (values suppressed):")
        print("\n".join(findings))
        return 1
    print(f"Local secret-pattern scan passed ({checked} text files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
