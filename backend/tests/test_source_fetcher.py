"""Offline downloader safeguards; fixture PDF bytes are not regulatory evidence."""

import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path


def load_fetcher(tmp_path, monkeypatch, payload):
    path = Path(__file__).resolve().parents[2] / "data/public/fetch_sources.py"
    spec = importlib.util.spec_from_file_location("test_mas_downloader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = tmp_path
    monkeypatch.setattr(sys, "argv", [str(path)])
    source = {
        "source_id": "MAS-TEST",
        "pdf_url": "https://www.mas.gov.sg/test.pdf",
        "source_url": "https://www.mas.gov.sg/test-source",
        "status_verification": "Old catalogue note",
    }
    previous = {
        **source,
        "sha256": hashlib.sha256(b"%PDF-test-pinned").hexdigest(),
        "status_verification": "Reviewed historical edition",
        "current_status_checked_at": "2026-10-17",
        "current_status_verification": "Later response reviewed separately",
    }
    (tmp_path / "source-evidence.json").write_text(json.dumps({"sources": [source]}))
    (tmp_path / "source-manifest.json").write_text(
        json.dumps({"checked_at": "2026-10-17", "sources": [previous]})
    )
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        assert timeout == 40
        response = io.BytesIO(payload)
        response.url = source["pdf_url"]
        return response

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    return module, previous, requests


def test_verified_retry_preserves_currency_review_and_pinned_bytes(tmp_path, monkeypatch):
    module, previous, requests = load_fetcher(tmp_path, monkeypatch, b"%PDF-test-pinned")
    assert module.main() == 0
    result = json.loads((tmp_path / "source-manifest.json").read_text())
    source = result["sources"][0]
    assert source["sha256"] == previous["sha256"]
    assert source["current_status_verification"] == previous["current_status_verification"]
    assert source["status_verification"] == previous["status_verification"]
    assert result["checked_at"] == "2026-10-17"
    assert (tmp_path / "downloads/MAS-TEST.pdf").read_bytes() == b"%PDF-test-pinned"
    assert requests[0].get_header("Referer") == previous["source_url"]
    assert "application/pdf" in requests[0].get_header("Accept")


def test_html_cannot_replace_verified_pdf_or_manifest(tmp_path, monkeypatch):
    module, _, _ = load_fetcher(tmp_path, monkeypatch, b"<html>Maintenance</html>")
    pinned_manifest = (tmp_path / "source-manifest.json").read_bytes()
    target = tmp_path / "downloads/MAS-TEST.pdf"
    target.parent.mkdir()
    target.write_bytes(b"%PDF-test-pinned")
    assert module.main() == 1
    assert (tmp_path / "source-manifest.json").read_bytes() == pinned_manifest
    assert target.read_bytes() == b"%PDF-test-pinned"
    failure = json.loads((tmp_path / "downloads/fetch-failure-report.json").read_text())
    assert failure["sources"][0]["fetch_status"] == "FAILED"
