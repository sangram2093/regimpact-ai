"""Rebuild transparent local fixtures from the checked-in public source manifest.

Run from any directory with Python 3.12. No network, AI inference or real human
approval is performed. Enterprise graph nodes are original synthetic examples.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
source = json.loads((DATA / "public" / "source-evidence.json").read_text(encoding="utf-8"))


def edge(
    edge_id: str, start: str, end: str, relationship: str, evidence_ids: list[str], reason: str
):
    return {
        "id": edge_id,
        "source_id": start,
        "target_id": end,
        "relationship": relationship,
        "status": "APPROVED",
        "evidence_ids": evidence_ids,
        "data_origin": "SYNTHETIC_HACKATHON",
        "provenance": {
            "proposed_by": "SEED",
            "decision_source": "GOLDEN_LABELS",
            "reason": reason,
            "reviewer": "Curated demonstration fixture",
            "reviewed_at": None,
            "model": None,
            "prompt_version": None,
            "vector_rank": None,
            "lexical_rank": None,
            "rrf_rank": None,
            "rrf_score": None,
            "alternative": None,
            "alternative_reason": None,
        },
    }


nodes = [
    ("PR-GIFT-01", "Responsible gifts and customer inducements", "POLICY_REQUIREMENT"),
    ("PR-IDENTITY-01", "Transparent representative identification", "POLICY_REQUIREMENT"),
    ("PR-CONSENT-01", "Permission before marketing contact", "POLICY_REQUIREMENT"),
    ("CO-GIFT-01", "Campaign gift approval and monitoring", "CONTROL_OBJECTIVE"),
    ("CO-GIFT-02", "Sales and telemarketing script assurance", "CONTROL_OBJECTIVE"),
    ("CO-IDENTITY-01", "Representative identification spot checks", "CONTROL_OBJECTIVE"),
    ("RT-CONDUCT", "Conduct risk", "RISK_TYPE"),
    ("RD-INDUCEMENT", "Inappropriate sales inducement", "RISK_DRIVER"),
    ("RD-TRANSPARENCY", "Unclear customer communication", "RISK_DRIVER"),
]
catalog_edges = [
    edge(
        "E-GIFT-CONTROL-01",
        "PR-GIFT-01",
        "CO-GIFT-01",
        "IMPLEMENTED_BY",
        [],
        ("Synthetic enterprise catalog: gift approval and monitoring implements the gifts policy."),
    ),
    edge(
        "E-GIFT-CONTROL-02",
        "PR-GIFT-01",
        "CO-GIFT-02",
        "IMPLEMENTED_BY",
        [],
        (
            "Synthetic enterprise catalog: script assurance implements "
            "responsible gift communication."
        ),
    ),
    edge(
        "E-IDENTITY-CONTROL-01",
        "PR-IDENTITY-01",
        "CO-IDENTITY-01",
        "IMPLEMENTED_BY",
        [],
        (
            "Synthetic enterprise catalog: spot checks implement "
            "representative identification policy."
        ),
    ),
]
CATALOG_TEXT = {
    "PR-GIFT-01": (
        "Gifts and promotional incentives must not pressure customers to "
        "purchase. Campaign owners review value, messaging and "
        "eligibility, including telemarketing scripts, and keep an "
        "approval record."
    ),
    "PR-IDENTITY-01": (
        "Representatives identify themselves, their institution and "
        "relevant third-party relationships before customer prospecting. "
        "Identification checks do not by themselves establish "
        "marketing-purpose disclosure or consent."
    ),
    "PR-CONSENT-01": (
        "Disclose the purpose of marketing contact and obtain permission "
        "before prospecting. Record verbal, written or event-registration "
        "consent and respect withdrawals across in-person and telephone "
        "channels."
    ),
    "CO-GIFT-01": (
        "Review gift eligibility and campaign messaging before release; "
        "sample approved campaigns for inducement concerns and retain "
        "review evidence."
    ),
    "CO-GIFT-02": (
        "Check sales and telephone scripts for inappropriate gift "
        "inducements; record assurance findings and remediation decisions."
    ),
    "CO-IDENTITY-01": (
        "Sample prospecting interactions for representative and "
        "institution identification; retain results and refer exceptions "
        "for review."
    ),
    "RT-CONDUCT": (
        "Risk of unfair customer outcomes caused by inappropriate marketing or sales conduct."
    ),
    "RD-INDUCEMENT": "Gifts, incentives or pressure may inappropriately "
    "influence a purchase decision.",
    "RD-TRANSPARENCY": (
        "Customers may not understand the representative identity, "
        "institution relationship, marketing purpose or consent choice."
    ),
}

catalog = {
    "disclosure": "Original SYNTHETIC_HACKATHON policies, controls and risk taxonomy; "
    "no employer data.",
    "nodes": [
        {
            "id": i,
            "title": t,
            "text": CATALOG_TEXT[i],
            "type": k,
            "data_origin": "SYNTHETIC_HACKATHON",
        }
        for i, t, k in nodes
    ],
    "edges": catalog_edges,
}

baseline_edges = []
for prefix, mandate, policy, driver, evidence_id in [
    ("GIFT", "M-GIFT", "PR-GIFT-01", "RD-INDUCEMENT", "SEG-FSG-GIFT"),
    ("IDENTITY", "M-IDENTITY", "PR-IDENTITY-01", "RD-TRANSPARENCY", "SEG-FSG-IDENTITY"),
]:
    baseline_edges.extend(
        [
            edge(
                f"E-{prefix}-POLICY",
                mandate,
                policy,
                "ADDRESSED_BY",
                [evidence_id],
                "Curated golden-label mapping connects the public safeguard to a synthetic policy. "
                "It is a demonstration fixture, not a live AI recommendation "
                "or institutional approval.",
            ),
            edge(
                f"E-{prefix}-RISK",
                mandate,
                "RT-CONDUCT",
                "CLASSIFIED_AS",
                [evidence_id],
                "Curated conduct-risk classification provides context only; "
                "it never propagates impact.",
            ),
            edge(
                f"E-{prefix}-DRIVER",
                mandate,
                driver,
                "DRIVEN_BY",
                [evidence_id],
                "Curated risk-driver classification provides context only; "
                "it never propagates impact.",
            ),
        ]
    )


def checks(pcs_target: bool, basis: str):
    return {
        "high_confidence_pcs_target": pcs_target,
        "applicable_global_overlay": True,
        "no_effect_result": "EFFECT_POSSIBLE",
        "human_change_confirmed": False,
        "scope_basis": basis,
        "decision_source": "GOLDEN_LABELS",
    }


baseline = {
    "instruments": [
        {
            "id": item["source_id"],
            "title": item["title"],
            "regulator": "MAS",
            "publication_date": item["publication_date"],
            "status": item["instrument_status"],
            "source_url": item["source_url"],
            "verification_status": "VERIFIED_PRIMARY_SOURCE",
            "data_origin": "PUBLIC_REGULATORY_SOURCE",
        }
        for item in source["sources"]
    ],
    "versions": [{"id": "VERSION-FSG-2016", "instrument_id": "MAS-FSG-G02-2016"}],
    "proposals": [
        {
            "id": "PROPOSAL-MAS-2023",
            "source_id": "MAS-P002-2023",
            "baseline_version_id": "VERSION-FSG-2016",
        }
    ],
    "provisions": [
        {
            "id": "PROVISION-GIFT",
            "regulation_version_id": "VERSION-FSG-2016",
            "title": "Gift safeguard",
            "evidence_ids": ["SEG-FSG-GIFT"],
        },
        {
            "id": "PROVISION-IDENTITY",
            "regulation_version_id": "VERSION-FSG-2016",
            "title": "Identity disclosure safeguard",
            "evidence_ids": ["SEG-FSG-IDENTITY"],
        },
    ],
    "mandates": [
        {
            "id": "M-GIFT",
            "title": "Prevent undue influence from gift offers",
            "provision_id": "PROVISION-GIFT",
            "evidence_ids": ["SEG-FSG-GIFT"],
            "status": "BASELINE_APPROVED",
            "data_origin": "PUBLIC_REGULATORY_SOURCE",
        },
        {
            "id": "M-IDENTITY",
            "title": "Identify the representative and institution",
            "provision_id": "PROVISION-IDENTITY",
            "evidence_ids": ["SEG-FSG-IDENTITY"],
            "status": "BASELINE_APPROVED",
            "data_origin": "PUBLIC_REGULATORY_SOURCE",
        },
        {
            "id": "M-INTENT-CONSENT",
            "title": "Disclose marketing intent and obtain consent",
            "provision_id": None,
            "evidence_ids": ["SEG-CP-CONSENT"],
            "status": "PROPOSED",
            "data_origin": "PUBLIC_REGULATORY_SOURCE",
        },
    ],
    "evidence": [
        {
            "id": segment["segment_id"],
            "source_id": segment["source_id"],
            "title": segment["section_path"],
            **{
                key: segment[key]
                for key in (
                    "source_url",
                    "paragraph_ref",
                    "page",
                    "text",
                    "text_kind",
                    "verification_status",
                    "data_origin",
                )
            },
        }
        for segment in source["segments"]
    ],
    "edges": baseline_edges,
    "proposed_change_statements": [
        {
            "id": "PCS-GIFT",
            "proposal_id": "PROPOSAL-MAS-2023",
            "summary": "Explicit gift inducement prohibition and telemarketing extension proposed.",
            "target_mandate_ids": ["M-GIFT"],
            "evidence_ids": ["SEG-CP-GIFT", "SEG-CP-TELEMARKETING"],
        },
        {
            "id": "PCS-LEGAL-FORCE",
            "proposal_id": "PROPOSAL-MAS-2023",
            "summary": "Proposed Notices affect safeguards for investment products "
            "and long-term A&H.",
            "target_mandate_ids": ["M-GIFT", "M-IDENTITY"],
            "global_scope": True,
            "evidence_ids": ["SEG-CP-LEGAL-FORCE"],
        },
        {
            "id": "PCS-INTENT-CONSENT",
            "proposal_id": "PROPOSAL-MAS-2023",
            "summary": "Disclose marketing purpose and obtain consent before prospecting.",
            "target_mandate_ids": ["M-INTENT-CONSENT"],
            "evidence_ids": ["SEG-CP-CONSENT"],
        },
    ],
    "changes": [
        {
            "id": "CHANGE-GIFT",
            "title": "Gift offers: stronger safeguards, wider reach",
            "classification": "MODIFIED",
            "change_nature": ["STRENGTHENED", "SCOPE_CHANGED", "LEGAL_FORCE_CHANGE_PROPOSED"],
            "summary": "MAS proposes an explicit prohibition on gift-based purchase inducement, "
            "telemarketing coverage and binding treatment for specified product categories.",
            "mandate_id": "M-GIFT",
            "baseline_evidence_ids": ["SEG-FSG-GIFT"],
            "proposal_evidence_ids": ["SEG-CP-GIFT", "SEG-CP-TELEMARKETING", "SEG-CP-LEGAL-FORCE"],
            "safety_checks": checks(
                True,
                "Gift language and channel scope are directly targeted. "
                "For the investment-product scenario, the proposed legal-force "
                "overlay also applies. All mandate mappings need individual review.",
            ),
        },
        {
            "id": "CHANGE-INTENT-CONSENT",
            "title": "Upfront intent disclosure and consent",
            "classification": "NEW",
            "change_nature": ["NEW_OBLIGATION", "SCOPE_CHANGED"],
            "summary": "If adopted, marketing purpose disclosure and consent "
            "would precede prospecting. "
            "This is distinct from the existing identity-disclosure safeguard.",
            "mandate_id": "M-INTENT-CONSENT",
            "baseline_evidence_ids": ["SEG-FSG-IDENTITY"],
            "proposal_evidence_ids": ["SEG-CP-CONSENT", "SEG-CP-TELEMARKETING"],
            "safety_checks": checks(
                True,
                "A genuinely new proposed intent/consent obligation. "
                "No approved mandate-specific mapping exists to reuse.",
            ),
        },
        {
            "id": "CHANGE-IDENTITY",
            "title": "Identity safeguard: scope review remains open",
            "classification": "UNRESOLVED",
            "change_nature": ["LEGAL_FORCE_CHANGE_PROPOSED"],
            "summary": "Identity disclosure has baseline treatment, but the proposed Notices and "
            "interaction with intent/consent need specialist confirmation. No unchanged "
            "classification is asserted.",
            "mandate_id": "M-IDENTITY",
            "baseline_evidence_ids": ["SEG-FSG-IDENTITY"],
            "proposal_evidence_ids": ["SEG-CP-LEGAL-FORCE", "SEG-CP-CONSENT"],
            "safety_checks": checks(
                False,
                "Absence of a direct wording change cannot establish "
                "no effect. Proposed binding treatment for investment products "
                "requires a scoped legal-force review before reuse.",
            ),
        },
    ],
    "scenario": {
        "id": "SCENARIO-MAS-2023",
        "title": "Public prospecting & telemarketing safeguards",
        "regulator": "MAS",
        "baseline_label": "IN FORCE — MAS Guideline (2016)",
        "proposal_label": "MAS consultation P002-2023",
        "baseline_version_id": "VERSION-FSG-2016",
        "proposal_id": "PROPOSAL-MAS-2023",
        "baseline_mandate_ids": ["M-GIFT", "M-IDENTITY"],
        "disclosure": "Curated local scenario for investment-product prospecting. "
        "Public MAS content "
        "is paraphrased; enterprise mappings are synthetic golden-label fixtures. "
        "No live AI run or real specialist approval is claimed. Legal-force scope "
        "blocks safe carry-forward in this fixture; test cases exercise eligible reuse.",
    },
}

for relative, value in [("seed/baseline.json", baseline), ("synthetic/catalog.json", catalog)]:
    target = DATA / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
