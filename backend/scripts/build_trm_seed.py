# ruff: noqa: E501 -- golden-label tables keep one obligation per line for review.
"""Build the MAS TRM final-instrument scenario from official paragraph excerpts.

Inputs: data/public/trm-paragraphs.json (verbatim in-scope paragraphs from the official
2019 consultation draft and the January 2021 final Guidelines, with page numbers).
Outputs: data/seed/trm_baseline.json, data/synthetic/trm_catalog.json and
data/seed/trm_demo_catalog.json.

Change classifications are team golden labels made by comparing each draft paragraph
with its final counterpart. Enterprise policies, controls and mappings are synthetic.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DRAFT, FINAL = "MAS-TRM-CP-2019", "MAS-TRM-2021"
DRAFT_URL = (
    "https://www.mas.gov.sg/-/media/Consultation-Paper-on-Proposed-Revisions-to-Technology-"
    "Risk-Management-Guidelines.pdf"
)
FINAL_URL = (
    "https://www.mas.gov.sg/-/media/MAS/Regulations-and-Financial-Stability/Regulatory-and-"
    "Supervisory-Framework/Risk-Management/TRM-Guidelines-18-January-2021.pdf"
)

# Synthetic enterprise catalog.
POLICIES = {
    "PR-TRM-UAM": (
        "User access management",
        "Grant access by role on least privilege and need-to-use; approve, change, review and "
        "revoke access promptly; log user access activity.",
    ),
    "PR-TRM-AUTH": (
        "Strong authentication standard",
        "Enforce strong passwords and multi-factor authentication for sensitive system "
        "functions and remote access.",
    ),
    "PR-TRM-PAM": (
        "Privileged and service accounts",
        "Restrict privileged access to need-to-use; log, monitor and review privileged, system "
        "and service account activity.",
    ),
    "PR-TRM-REMOTE": (
        "Secure remote access",
        "Encrypt remote connections, require strong authentication and allow only devices that "
        "meet security standards.",
    ),
    "PR-TRM-VENDOR": (
        "Service provider access",
        "Apply the same access restrictions and monitoring to service providers as to staff.",
    ),
    "PR-TRM-VA": (
        "Vulnerability assessment standard",
        "Run regular vulnerability assessments covering configurations, open ports, "
        "applications and common web vulnerabilities.",
    ),
    "PR-TRM-PT": (
        "Penetration testing standard",
        "Commission independent penetration tests of internet-facing and critical systems on a "
        "defined frequency and after major changes.",
    ),
    "PR-TRM-EXERCISE": (
        "Cyber exercises and attack simulation",
        "Run scenario-based cyber exercises and adversarial attack simulations with defined rules "
        "of engagement and threat-intelligence-based scenarios.",
    ),
    "PR-TRM-REMEDIATE": (
        "Security issue remediation",
        "Track, prioritise and resolve assessment findings by severity within defined timeframes, "
        "with risk acceptance for deviations.",
    ),
    "PR-TRM-API": (
        "API security standard",
        "Vet API partners, secure API development and keys, test before production, log and "
        "monitor API usage, and protect API capacity.",
    ),
    "PR-TRM-OSS": (
        "Third-party and open-source code",
        "Review and test third-party and open-source code before use, and track its updates and "
        "reported vulnerabilities.",
    ),
}
CONTROLS = {
    "CO-TRM-UAM-01": ("Quarterly user access recertification", "PR-TRM-UAM"),
    "CO-TRM-UAM-02": ("Joiner-mover-leaver access revocation", "PR-TRM-UAM"),
    "CO-TRM-AUTH-01": ("MFA enforcement for sensitive functions", "PR-TRM-AUTH"),
    "CO-TRM-PAM-01": ("Privileged session logging and review", "PR-TRM-PAM"),
    "CO-TRM-REMOTE-01": ("Managed-device check for remote access", "PR-TRM-REMOTE"),
    "CO-TRM-VENDOR-01": ("Vendor access monitoring", "PR-TRM-VENDOR"),
    "CO-TRM-VA-01": ("Scheduled vulnerability scanning coverage", "PR-TRM-VA"),
    "CO-TRM-PT-01": ("Annual penetration test of internet-facing systems", "PR-TRM-PT"),
    "CO-TRM-EXERCISE-01": ("Annual scenario-based cyber exercise", "PR-TRM-EXERCISE"),
    "CO-TRM-EXERCISE-02": ("Red-team attack simulation under rules of engagement", "PR-TRM-EXERCISE"),
    "CO-TRM-REMEDIATE-01": ("Remediation tracking against severity deadlines", "PR-TRM-REMEDIATE"),
    "CO-TRM-API-01": ("API partner vetting and access review", "PR-TRM-API"),
    "CO-TRM-API-02": ("API monitoring, rate limiting and key revocation", "PR-TRM-API"),
}
RISK_TYPES = {
    "RT-TRM-CYBER": "Cyber risk",
    "RT-TRM-TECH": "Technology risk",
    "RT-TRM-THIRD": "Third-party risk",
}
RISK_DRIVERS = {
    "RD-TRM-ACCESS": "Excessive or stale access",
    "RD-TRM-AUTH": "Weak authentication",
    "RD-TRM-UNTESTED": "Untested cyber defences",
    "RD-TRM-VULN": "Unremediated vulnerabilities",
    "RD-TRM-API": "Insecure third-party API connections",
    "RD-TRM-CODE": "Unvetted third-party code",
}

SECTIONS = {
    "9.1": "User access management",
    "9.2": "Privileged access management",
    "9.3": "Remote access management",
    "13.1": "Vulnerability assessment",
    "13.2": "Penetration testing",
    "13.3": "Cyber exercises",
    "13.4": "Adversarial attack simulation exercise",
    "13.5": "Intelligence-based scenario design",
    "13.6": "Remediation management",
    "6.4": "Application programming interface development",
}

# Baseline obligations from the 2019 draft: draft ref -> (title, policy, risk type, driver).
MANDATES = {
    "9.1.1": ("Apply never-alone, segregation of duties and least privilege", "PR-TRM-UAM", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "9.1.2": ("Run an approved process to provision and revoke access", "PR-TRM-UAM", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "9.1.3": ("Log user access activity under unique identities", "PR-TRM-UAM", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "9.1.4": ("Enforce a strong password policy", "PR-TRM-AUTH", "RT-TRM-CYBER", "RD-TRM-AUTH"),
    "9.1.5": ("Use multi-factor authentication for critical functions", "PR-TRM-AUTH", "RT-TRM-CYBER", "RD-TRM-AUTH"),
    "9.1.6": ("Review user access periodically", "PR-TRM-UAM", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "9.1.7": ("Grant access only on a need-to-use basis and revoke promptly", "PR-TRM-UAM", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "9.1.8": ("Restrict and monitor service providers like staff", "PR-TRM-VENDOR", "RT-TRM-THIRD", "RD-TRM-ACCESS"),
    "9.2.1": ("Limit, log and review privileged access", "PR-TRM-PAM", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "9.2.2": ("Monitor system and service accounts", "PR-TRM-PAM", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "9.3.1": ("Encrypt remote access and require strong authentication", "PR-TRM-REMOTE", "RT-TRM-CYBER", "RD-TRM-AUTH"),
    "9.3.2": ("Allow remote access only from hardened devices", "PR-TRM-REMOTE", "RT-TRM-CYBER", "RD-TRM-ACCESS"),
    "13.1.1": ("Perform regular vulnerability assessments", "PR-TRM-VA", "RT-TRM-CYBER", "RD-TRM-VULN"),
    "13.1.2": ("Cover minimum scope in vulnerability assessments", "PR-TRM-VA", "RT-TRM-CYBER", "RD-TRM-VULN"),
    "13.2.1": ("Conduct black-box and grey-box penetration tests", "PR-TRM-PT", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.2.2": ("Consider a bug bounty programme to complement testing", "PR-TRM-PT", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.2.3": ("Penetration-test production with proper safeguards", "PR-TRM-PT", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.2.4": ("Set penetration test frequency by risk and exposure", "PR-TRM-PT", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.3.1": ("Run scenario-based cyber exercises and review plans", "PR-TRM-EXERCISE", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.3.2": ("Involve stakeholders in cyber exercises", "PR-TRM-EXERCISE", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.4.1": ("Consider adversarial attack simulation exercises", "PR-TRM-EXERCISE", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.4.2": ("Define rules of engagement for red-team exercises", "PR-TRM-EXERCISE", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.5.1": ("Base red-team scenarios on real cyber incidents", "PR-TRM-EXERCISE", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.5.2": ("Alternatively design scenarios from threat intelligence", "PR-TRM-EXERCISE", "RT-TRM-CYBER", "RD-TRM-UNTESTED"),
    "13.6.1": ("Track and resolve assessment findings by severity", "PR-TRM-REMEDIATE", "RT-TRM-CYBER", "RD-TRM-VULN"),
    "6.4.1": ("Safeguard the development and provision of APIs", "PR-TRM-API", "RT-TRM-TECH", "RD-TRM-API"),
    "6.4.2": ("Control access to designated API services", "PR-TRM-API", "RT-TRM-CYBER", "RD-TRM-API"),
    "6.4.3": ("Vet third parties before granting API access", "PR-TRM-API", "RT-TRM-THIRD", "RD-TRM-API"),
    "6.4.4": ("Assess risk before third parties connect via APIs", "PR-TRM-API", "RT-TRM-THIRD", "RD-TRM-API"),
    "6.4.5": ("Set secure API standards and protect keys and tokens", "PR-TRM-API", "RT-TRM-CYBER", "RD-TRM-API"),
    "6.4.6": ("Encrypt sensitive data sent through APIs", "PR-TRM-API", "RT-TRM-CYBER", "RD-TRM-API"),
    "6.4.7": ("Test APIs before production and log third-party sessions", "PR-TRM-API", "RT-TRM-THIRD", "RD-TRM-API"),
    "6.4.8": ("Monitor APIs in real time and revoke keys on breach", "PR-TRM-API", "RT-TRM-CYBER", "RD-TRM-API"),
    "6.4.9": ("Handle high API volumes and mitigate denial of service", "PR-TRM-API", "RT-TRM-TECH", "RD-TRM-API"),
}

# Golden labels: draft ref -> (final ref or None, classification, nature, explanation).
LABELS = {
    "9.1.1": ("9.1.1", "MODIFIED", ["SCOPE_CHANGED", "CLARIFIED"], "Access must now follow the roles of staff, contractors and service providers, and the principles apply to 'sensitive' rather than 'critical' functions."),
    "9.1.2": ("9.1.2", "MODIFIED", ["STRENGTHENED", "CLARIFIED"], "The access process must also cover changes to access rights, and approval may come from appropriate parties such as the asset owner."),
    "9.1.3": ("9.1.3", "UNCHANGED", [], "Only 'For accountability' became 'For proper accountability'; the logging obligation is the same."),
    "9.1.4": ("9.1.4", "UNCHANGED", [], "Word for word identical."),
    "9.1.5": ("9.1.5", "MODIFIED", ["SCOPE_CHANGED"], "Multi-factor authentication now applies to 'sensitive' rather than 'critical' system functions, and protects 'data' rather than 'information'."),
    "9.1.6": ("9.1.6", "MODIFIED", ["CLARIFIED"], "Reviews may be performed by appropriate parties, and must catch inappropriate access rather than only incorrectly provisioned access."),
    "9.1.7": ("9.1.7", "UNCHANGED", [], "Reworded only: access remains need-to-use and must be revoked promptly when no longer needed."),
    "9.1.8": ("9.1.8", "UNCHANGED", [], "Word for word identical."),
    "9.2.1": ("9.2.1", "UNCHANGED", [], "Only 'granted with' became 'granted'."),
    "9.2.2": ("9.2.2", "UNCHANGED", [], "Only 'the operating systems' became 'operating systems'."),
    "9.3.1": ("9.3.1", "UNCHANGED", [], "Only 'connection' became 'connections'."),
    "9.3.2": ("9.3.2", "MODIFIED", ["CLARIFIED"], "Remote devices must be 'secured' rather than 'hardened' according to the security standards, a broader requirement."),
    "13.1.1": ("13.1.1", "UNCHANGED", [], "Only the word 'IT' was added twice."),
    "13.1.2": ("13.1.2", "MODIFIED", ["SCOPE_CHANGED"], "Minimum assessment scope now names open network ports and application vulnerabilities, and drops unapproved applications and services."),
    "13.2.1": ("13.2.1", "UNCHANGED", [], "Word for word identical."),
    "13.2.2": ("13.2.2", "UNCHANGED", [], "Editorial only: 'test' became 'conduct PT on' and 'IT' was added."),
    "13.2.3": ("13.2.3", "UNCHANGED", [], "Word for word identical."),
    "13.2.4": ("13.2.4", "UNCHANGED", [], "Word for word identical."),
    "13.3.1": ("13.3.1", "MODIFIED", ["CLARIFIED"], "Exercises must 'validate' plans; the words 'and review' were removed, so the expected outcome changed slightly."),
    "13.3.2": ("13.3.2", "UNCHANGED", [], "Word for word identical."),
    "13.4.1": ("13.4.1", "MODIFIED", ["STRENGTHENED"], "'Is encouraged to' became 'should': adversarial attack simulation moved from optional good practice to an expected practice."),
    "13.4.2": ("13.4.2", "UNCHANGED", [], "Word for word identical."),
    "13.5.1": ("13.5.1", "MODIFIED", ["SCOPE_CHANGED"], "Threat scenarios now apply to any cyber security assessment, not only red-team exercises, and use challenging but plausible threats rather than past incidents."),
    "13.5.2": ("13.5.2", "MODIFIED", ["CLARIFIED"], "Threat intelligence is no longer 'an alternative' to incident-based scenarios but an additional design approach."),
    "13.6.1": ("13.6.1", "UNCHANGED", [], "Only 'remediation management process' became 'remediation process'."),
    "6.4.1": ("6.4.1", "UNCHANGED", [], "Descriptive wording only ('proprietary' removed, 'may collaborate'); the safeguard obligation is the same."),
    "6.4.2": (None, "REMOVED", [], "This draft paragraph is not kept as a separate paragraph in the final text; confirm whether other API controls cover it before retiring the mapping."),
    "6.4.3": ("6.4.2", "MODIFIED", ["CLARIFIED"], "Vetting criteria now consider the third party's cyber security posture rather than its security policy."),
    "6.4.4": ("6.4.3", "UNCHANGED", [], "Editorial only: 'a' and 'IT' added."),
    "6.4.5": ("6.4.4", "UNCHANGED", [], "Word for word identical."),
    "6.4.6": ("6.4.5", "UNCHANGED", [], "Word for word identical."),
    "6.4.7": ("6.4.6", "MODIFIED", ["STRENGTHENED"], "Third-party API sessions must now be logged, including date and time, instead of the FI only having the ability to log them."),
    "6.4.8": ("6.4.7", "MODIFIED", ["CLARIFIED"], "Real-time monitoring is now framed as detective measures such as real-time monitoring and alerting technologies."),
    "6.4.9": ("6.4.8", "MODIFIED", ["STRENGTHENED"], "The FI must ensure adequate system capacity and mitigate cyber threats such as DoS attacks; the proportionality wording was removed."),
}
NEW = {
    "6.1.3": ("Govern third-party and open-source code before use", "New in the final text: a policy and procedure must ensure third-party and open-source code is reviewed and tested before integration."),
    "6.1.4": ("Track vulnerabilities in third-party and open-source code", "New in the final text: track updates and reported vulnerabilities for third-party and open-source code used in the FI's software."),
}


def ref_id(ref: str) -> str:
    return ref.replace(".", "-")


def build() -> None:
    sources = json.loads((DATA / "public" / "trm-paragraphs.json").read_text(encoding="utf-8"))
    draft = {p["ref"]: p for p in sources["sources"][DRAFT]["paragraphs"]}
    final = {p["ref"]: p for p in sources["sources"][FINAL]["paragraphs"]}
    assert set(MANDATES) == set(LABELS) <= set(draft), set(MANDATES) ^ set(LABELS)

    def evidence(source_id: str, para: dict) -> dict:
        is_draft = source_id == DRAFT
        return {
            "id": f"EV-TRM-{'2019' if is_draft else '2021'}-{ref_id(para['ref'])}",
            "source_id": source_id,
            "title": ("TRM consultation draft (2019)" if is_draft else "TRM Guidelines (2021)")
            + f" · {para['ref']}",
            "source_url": DRAFT_URL if is_draft else FINAL_URL,
            "paragraph_ref": para["ref"],
            "page": para["page"],
            "text": para["text"],
            "text_kind": "VERIFIED_EXCERPT",
            "verification_status": "EXTRACTED_FROM_OFFICIAL_PDF",
            "data_origin": "PUBLIC_REGULATORY_SOURCE",
        }

    evidence_items, mandates, provisions, edges, pcs, changes = [], [], [], [], [], []
    section_evidence: dict[str, list[str]] = {}
    for ref in MANDATES:
        item = evidence(DRAFT, draft[ref])
        evidence_items.append(item)
        section_evidence.setdefault(".".join(ref.split(".")[:2]), []).append(item["id"])
    for ref in [label[0] for label in LABELS.values() if label[0]] + list(NEW):
        evidence_items.append(evidence(FINAL, final[ref]))
    for section, ids in section_evidence.items():
        provisions.append(
            {
                "id": f"PROV-TRM-{ref_id(section)}",
                "regulation_version_id": "VERSION-TRM-2019",
                "title": f"{section} {SECTIONS[section]}",
                "evidence_ids": ids,
            }
        )
    for ref, (title, policy, risk, driver) in MANDATES.items():
        mandate_id = f"M-TRM-{ref_id(ref)}"
        draft_ev = f"EV-TRM-2019-{ref_id(ref)}"
        mandates.append(
            {
                "id": mandate_id,
                "title": title,
                "provision_id": f"PROV-TRM-{ref_id('.'.join(ref.split('.')[:2]))}",
                "evidence_ids": [draft_ev],
                "status": "BASELINE_APPROVED",
                "data_origin": "PUBLIC_REGULATORY_SOURCE",
            }
        )
        for suffix, relationship, target, reason in (
            ("POLICY", "ADDRESSED_BY", policy, f"{POLICIES[policy][0]} directly implements draft paragraph {ref}."),
            ("RISK", "CLASSIFIED_AS", risk, f"Draft paragraph {ref} manages {RISK_TYPES[risk].lower()}."),
            ("DRIVER", "DRIVEN_BY", driver, f"Draft paragraph {ref} addresses the driver '{RISK_DRIVERS[driver].lower()}'."),
        ):
            edges.append(
                {
                    "id": f"E-TRM-{ref_id(ref)}-{suffix}",
                    "source_id": mandate_id,
                    "target_id": target,
                    "relationship": relationship,
                    "status": "APPROVED",
                    "evidence_ids": [draft_ev],
                    "data_origin": "SYNTHETIC_HACKATHON",
                    "provenance": {
                        "proposed_by": "SEED",
                        "decision_source": "GOLDEN_LABELS",
                        "reason": f"Approved during consultation preparation: {reason} "
                        "Synthetic enterprise mapping curated as a golden label.",
                        "reviewer": "Curated demonstration fixture",
                    },
                }
            )
        final_ref, classification, nature, explanation = LABELS[ref]
        final_ev = [f"EV-TRM-2021-{ref_id(final_ref)}"] if final_ref else []
        unchanged = classification == "UNCHANGED"
        if not unchanged:
            pcs.append(
                {
                    "id": f"PCS-TRM-{ref_id(ref)}",
                    "proposal_id": "CHANGE-SOURCE-TRM-2021",
                    "summary": explanation,
                    "target_mandate_ids": [mandate_id],
                    "global_scope": False,
                    "evidence_ids": final_ev or [draft_ev],
                }
            )
        location = f"final {final_ref}" if final_ref else "the final text"
        changes.append(
            {
                "id": f"CHANGE-TRM-{ref_id(ref)}",
                "title": f"{ref} {title}",
                "classification": classification,
                "change_nature": nature,
                "summary": explanation,
                "mandate_id": mandate_id,
                "baseline_evidence_ids": [draft_ev],
                "proposal_evidence_ids": final_ev,
                "is_proposal": False,
                "safety_checks": {
                    "high_confidence_pcs_target": not unchanged,
                    "applicable_global_overlay": False,
                    "no_effect_result": "NO_EFFECT_SUPPORTED" if unchanged else "EFFECT_POSSIBLE",
                    "human_change_confirmed": True,
                    "scope_basis": (
                        f"Draft {ref} and {location} compared paragraph by paragraph. {explanation}"
                    ),
                    "decision_source": "GOLDEN_LABELS",
                },
            }
        )
    for ref, (title, explanation) in NEW.items():
        mandate_id = f"M-TRM-NEW-{ref_id(ref)}"
        final_ev = f"EV-TRM-2021-{ref_id(ref)}"
        mandates.append(
            {
                "id": mandate_id,
                "title": title,
                "provision_id": None,
                "evidence_ids": [final_ev],
                "status": "PROPOSED",
                "data_origin": "PUBLIC_REGULATORY_SOURCE",
            }
        )
        pcs.append(
            {
                "id": f"PCS-TRM-NEW-{ref_id(ref)}",
                "proposal_id": "CHANGE-SOURCE-TRM-2021",
                "summary": explanation,
                "target_mandate_ids": [mandate_id],
                "global_scope": False,
                "evidence_ids": [final_ev],
            }
        )
        changes.append(
            {
                "id": f"CHANGE-TRM-NEW-{ref_id(ref)}",
                "title": f"{ref} {title}",
                "classification": "NEW",
                "change_nature": ["NEW_OBLIGATION"],
                "summary": explanation,
                "mandate_id": mandate_id,
                "baseline_evidence_ids": [],
                "proposal_evidence_ids": [final_ev],
                "is_proposal": False,
                "safety_checks": {
                    "high_confidence_pcs_target": True,
                    "applicable_global_overlay": False,
                    "no_effect_result": "EFFECT_POSSIBLE",
                    "human_change_confirmed": True,
                    "scope_basis": f"Final paragraph {ref} has no counterpart in the 2019 draft.",
                    "decision_source": "GOLDEN_LABELS",
                },
            }
        )
    baseline = {
        "instruments": [
            {
                "id": DRAFT,
                "title": "Technology Risk Management Guidelines — consultation draft (P003-2019)",
                "regulator": "MAS",
                "publication_date": "2019-03-07",
                "status": "CONSULTATION_DRAFT",
                "source_url": DRAFT_URL,
                "verification_status": "VERIFIED_PRIMARY_SOURCE",
            },
            {
                "id": FINAL,
                "title": "Technology Risk Management Guidelines (January 2021)",
                "regulator": "MAS",
                "publication_date": "2021-01-18",
                "status": "IN_FORCE",
                "source_url": FINAL_URL,
                "verification_status": "VERIFIED_PRIMARY_SOURCE",
            },
        ],
        "versions": [
            {
                "id": "VERSION-TRM-2019",
                "instrument_id": DRAFT,
                "legal_force": "GUIDANCE",
                "status": "CONSULTATION_DRAFT",
            }
        ],
        "proposals": [
            {
                "id": "CHANGE-SOURCE-TRM-2021",
                "source_id": FINAL,
                "baseline_version_id": "VERSION-TRM-2019",
                "status": "FINAL",
                "legal_force_after": "GUIDANCE",
            }
        ],
        "provisions": provisions,
        "mandates": mandates,
        "evidence": evidence_items,
        "edges": edges,
        "proposed_change_statements": pcs,
        "changes": changes,
        "scenario": {
            "id": "SCENARIO-TRM-2021",
            "title": "Technology risk: from consultation draft to final rules",
            "regulator": "MAS",
            "baseline_label": "Prepared from the TRM consultation draft (March 2019)",
            "proposal_label": "MAS TRM Guidelines, January 2021",
            "status": "FINAL",
            "proposal_notice": "FINAL GUIDELINES — ISSUED 18 JANUARY 2021",
            "context_note": "The bank mapped the March 2019 consultation draft. "
            "MAS then issued the final Guidelines; only what changed needs fresh review.",
            "legal_force_note": "Both texts are MAS guidelines; legal force did not change.",
            "suggested_questions": [
                "Which access control obligations changed in the final guidelines, and which "
                "controls should we review?",
                "Why does the adversarial attack simulation obligation need review?",
                "Where are the coverage gaps for the new open-source code obligations?",
            ],
            "baseline_version_id": "VERSION-TRM-2019",
            "proposal_id": "CHANGE-SOURCE-TRM-2021",
            "baseline_mandate_ids": [f"M-TRM-{ref_id(ref)}" for ref in MANDATES],
            "disclosure": "Public MAS sources: verbatim paragraph excerpts from the March 2019 "
            "consultation draft and the January 2021 final Guidelines, chapters 6.4, 9 and 13 "
            "plus new paragraphs 6.1.3-6.1.4. Change classifications are team golden labels. "
            "Enterprise policies, controls and mappings are synthetic.",
        },
    }
    catalog = {
        "disclosure": "Synthetic enterprise technology-risk catalog for the hackathon "
        "demonstration. No institution's real policies or controls.",
        "nodes": [
            {"id": pid, "title": title, "type": "POLICY_REQUIREMENT", "text": text,
             "data_origin": "SYNTHETIC_HACKATHON"}
            for pid, (title, text) in POLICIES.items()
        ]
        + [
            {"id": cid, "title": title, "type": "CONTROL_OBJECTIVE", "text": title,
             "data_origin": "SYNTHETIC_HACKATHON"}
            for cid, (title, _) in CONTROLS.items()
        ]
        + [
            {"id": rid, "title": title, "type": "RISK_TYPE", "text": title,
             "data_origin": "SYNTHETIC_HACKATHON"}
            for rid, title in RISK_TYPES.items()
        ]
        + [
            {"id": rid, "title": title, "type": "RISK_DRIVER", "text": title,
             "data_origin": "SYNTHETIC_HACKATHON"}
            for rid, title in RISK_DRIVERS.items()
        ],
        "edges": [
            {
                "id": f"E-{cid}",
                "source_id": policy,
                "target_id": cid,
                "relationship": "IMPLEMENTED_BY",
                "status": "APPROVED",
                "evidence_ids": [],
                "data_origin": "SYNTHETIC_HACKATHON",
                "provenance": {
                    "proposed_by": "SEED",
                    "decision_source": "GOLDEN_LABELS",
                    "reason": f"Synthetic enterprise catalog: {title.lower()} implements "
                    f"{POLICIES[policy][0].lower()}.",
                    "reviewer": "Curated demonstration fixture",
                },
            }
            for cid, (title, policy) in CONTROLS.items()
        ],
    }
    guide = {
        "scenario_id": "SCENARIO-TRM-2021",
        "title": "Prepared on the draft, ready for the final rules",
        "baseline": "Prepared baseline: MAS TRM consultation draft (March 2019), "
        "34 approved obligations",
        "comparison": "Final rules: MAS Technology Risk Management Guidelines (January 2021)",
        "notice": "Both official PDFs are fingerprinted. Change labels compare each draft paragraph "
        "with the final text; enterprise policies and controls are synthetic.",
        "source_ids": [DRAFT, FINAL],
        "steps": [
            {"label": "1. See the two official texts", "path": "/sources"},
            {"label": "2. Reuse what still holds", "path": "/delta-review"},
            {"label": "3. A quiet but material change", "path": "/changes/CHANGE-TRM-13-4-1"},
            {"label": "4. Trace affected controls", "path": "/impact"},
            {"label": "5. Ask Gemini with evidence", "path": "/ask"},
        ],
    }
    write = lambda path, value: path.write_text(  # noqa: E731
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write(DATA / "seed" / "trm_baseline.json", baseline)
    write(DATA / "synthetic" / "trm_catalog.json", catalog)
    write(DATA / "seed" / "trm_demo_catalog.json", guide)
    counts = {
        label: sum(1 for value in LABELS.values() if value[1] == label)
        for label in ("UNCHANGED", "MODIFIED", "REMOVED")
    }
    print({"mandates": len(MANDATES), "new": len(NEW), **counts, "mappings": len(edges)})


if __name__ == "__main__":
    build()
