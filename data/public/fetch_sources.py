"""Fetch only the declared MAS PDFs; keep originals outside version control.

Run from any directory: python data/public/fetch_sources.py
Uses the standard library; never accepts arbitrary source URLs or logs response bodies.
Existing source-manifest.json checksums are preserved unless --accept-updated is given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
MAX_PDF_BYTES = 20 * 1024 * 1024
PUBLIC_PDF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--accept-updated",
        action="store_true",
        help="Explicitly accept a changed official PDF checksum.",
    )
    args = parser.parse_args()
    evidence = json.loads((BASE / "source-evidence.json").read_text(encoding="utf-8"))
    manifest_path = BASE / "source-manifest.json"
    prior = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {"sources": []}
    )
    previous = {item["source_id"]: item for item in prior["sources"]}
    output = {**prior, "schema_version": "1.0", "sources": []}
    failures = 0
    download_dir = BASE / "downloads"
    download_dir.mkdir(exist_ok=True)
    for source in evidence["sources"]:
        entry = dict(source)
        # Downloading a historical PDF must not erase a later source-currency review.
        for field in (
            "status_verification",
            "current_status_checked_at",
            "current_status_verification",
            "current_status_sources",
            "evidence_verification",
        ):
            if field in previous.get(source["source_id"], {}):
                entry[field] = previous[source["source_id"]][field]
        entry["attempted_at"] = datetime.now(UTC).isoformat()
        entry["retrieved_at"] = None
        entry["sha256"] = None
        entry["local_path"] = None
        url = source["pdf_url"]
        try:
            if (
                urlparse(url).hostname != "www.mas.gov.sg"
                or urlparse(url).scheme != "https"
            ):
                raise ValueError("Only declared HTTPS MAS URLs are permitted")
            referer = source["source_url"]
            if (
                urlparse(referer).hostname != "www.mas.gov.sg"
                or urlparse(referer).scheme != "https"
            ):
                raise ValueError("Only declared HTTPS MAS source pages are permitted")
            request = Request(
                url,
                headers={**PUBLIC_PDF_HEADERS, "Referer": referer},
            )
            with urlopen(request, timeout=40) as response:
                if (
                    urlparse(response.url).hostname != "www.mas.gov.sg"
                    or urlparse(response.url).scheme != "https"
                ):
                    raise ValueError(
                        "Unexpected source redirect; manual review required"
                    )
                payload = response.read(MAX_PDF_BYTES + 1)
            if len(payload) > MAX_PDF_BYTES or not payload.startswith(b"%PDF-"):
                raise ValueError("Response is not an acceptable PDF")
            digest = hashlib.sha256(payload).hexdigest()
            expected = previous.get(source["source_id"], {}).get("sha256")
            if expected and expected != digest and not args.accept_updated:
                raise ValueError(
                    "Source checksum changed; inspect the update before using --accept-updated"
                )
            filename = source["source_id"] + ".pdf"
            (download_dir / filename).write_bytes(payload)
            entry.update(
                sha256=digest,
                local_path=f"downloads/{filename}",
                byte_length=len(payload),
                fetch_status="FETCHED",
                retrieved_at=datetime.now(UTC).isoformat(),
            )
            print(
                f"{source['source_id']}: FETCHED {len(payload)} bytes; SHA-256 {digest}"
            )
        except (HTTPError, URLError, OSError, ValueError) as exc:
            failures += 1
            entry.update(fetch_status="FAILED", fetch_error=str(exc))
            if source["source_id"] in previous:
                entry["previous_success"] = previous[source["source_id"]]
            print(f"{source['source_id']}: FAILED: {exc}")
        output["sources"].append(entry)
    # Write a failure report separately so a failed attempt cannot erase trusted checksums.
    target = (
        BASE / "downloads" / "fetch-failure-report.json" if failures else manifest_path
    )
    target.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
