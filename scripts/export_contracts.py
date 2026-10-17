"""Export canonical OpenAPI and seed JSON schemas from the installed backend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if committed schemas drift."
    )
    args = parser.parse_args()
    from app.domain.models import SeedBundle
    from app.main import app

    artifacts = {
        "openapi.json": app.openapi(),
        "seed.schema.json": SeedBundle.model_json_schema(),
    }
    failures = []
    for filename, schema in artifacts.items():
        path = ROOT / "schemas" / filename
        expected = (
            json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        )
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                failures.append(filename)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
            print(f"Exported schemas/{filename}")
    if failures:
        print("Contract drift: " + ", ".join(failures))
        print("Run python scripts/export_contracts.py and review the schema diff.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
