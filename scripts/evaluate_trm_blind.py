"""Label-blind check: Gemini sees only the draft and final paragraph texts for each change.

The context omits the stored classification, change summary, change statements and
safety scope notes, so the model cannot copy the team label. Labels are still team-made,
so this is a development measurement, not an independent evaluation.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai.google_client import GoogleGenAITransport, create_vertex_client  # noqa: E402
from app.services.ai_workflows import BoundedWorkflowService  # noqa: E402

bundle = json.loads((ROOT / "data/seed/trm_baseline.json").read_text(encoding="utf-8"))
evidence = {e["id"]: e for e in bundle["evidence"]}
mandates = {m["id"]: m for m in bundle["mandates"]}
sources = [i | {"legal_force": "GUIDANCE"} for i in bundle["instruments"]]


def context(change: dict) -> dict:
    ids = change["baseline_evidence_ids"] + change["proposal_evidence_ids"]
    mandate = mandates[change["mandate_id"]]
    return {
        "sources": sources,
        "evidence": [evidence[i] for i in ids],
        "mandates": [mandate],
        "mandate_ids": [mandate["id"]],
        "entity_ids": [mandate["id"]],
        "proposal_notice": "Compare the 2019 consultation draft paragraph with the January 2021 "
        "final guideline paragraph. A missing paragraph means none exists in that version.",
        "proposed_change_statements": [],
        "change": {
            "id": change["id"],
            "mandate_id": change["mandate_id"],
            "baseline_evidence_ids": change["baseline_evidence_ids"],
            "proposal_evidence_ids": change["proposal_evidence_ids"],
        },
        "high_confidence_pcs_target": False,
        "applicable_global_overlay": False,
    }


async def main() -> None:
    client = create_vertex_client(os.environ["GCP_PROJECT_ID"], "global")
    service = BoundedWorkflowService(GoogleGenAITransport(client=client, model="gemini-3.5-flash"))
    rows = []
    try:
        for change in bundle["changes"]:
            result = await service.run("change-effect", context(change))
            predicted = (result.output or {}).get("classification")
            rows.append(
                {
                    "change_id": change["id"],
                    "golden": change["classification"],
                    "predicted": predicted,
                    "no_effect": (result.output or {}).get("no_effect_result"),
                    "status": result.status,
                    "reason": (result.output or {}).get("reason", "")[:220],
                }
            )
            print(json.dumps(rows[-1]), flush=True)
    finally:
        await client.aio.aclose()
    valid = [r for r in rows if r["predicted"]]
    unsafe = [
        r["change_id"]
        for r in valid
        if r["predicted"] == "UNCHANGED" and r["golden"] != "UNCHANGED"
    ]
    disagreements = [r for r in valid if r["predicted"] != r["golden"]]
    summary = {
        "kind": "LABEL_BLIND_DEVELOPMENT_CHECK",
        "inputs": "draft and final paragraph text only; no stored label, summary or statements",
        "label_source": "Team golden labels; not independent",
        "model": "gemini-3.5-flash, prompt change-effect-v1",
        "runs": len(rows),
        "validated_outputs": len(valid),
        "agreement": len(valid) - len(disagreements),
        "unsafe_unchanged_predictions": unsafe,
        "by_label": {
            label: f"{sum(1 for r in valid if r['golden'] == label and r['predicted'] == label)}/"
            f"{sum(1 for r in valid if r['golden'] == label)}"
            for label in ("UNCHANGED", "MODIFIED", "REMOVED", "NEW")
        },
        "disagreements": [
            {k: r[k] for k in ("change_id", "golden", "predicted", "reason")} for r in disagreements
        ],
    }
    out = ROOT / ".local/evaluation"
    out.mkdir(exist_ok=True)
    (out / "trm-change-effect-blind.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


asyncio.run(main())
