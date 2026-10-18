# RegImpact AI — User guide

Updated 18 October 2026. This guide walks through every screen of RegImpact AI using the **Technology risk · 2021 final** example. The example starts with the regulation's official documents and ends with an audited, human-approved review.

- Application: <https://regimpact-ai.web.app>
- Submission page (deck and video): <https://regimpact-ai.web.app/submission/>
- Source code: <https://github.com/sangram2093/regimpact-ai>

---

## 1. What RegImpact AI does

When a regulator revises its rules, a bank must work out which of its earlier decisions still hold. Those decisions link each obligation to the policies and controls that implement it. RegImpact AI keeps the evidence and reasoning behind every decision. When the rules change, it:

1. compares the old and new regulatory text, paragraph by paragraph;
2. reuses decisions whose obligations did not change, but only after four safeguards pass and a specialist confirms;
3. sends everything that did change to individual human review;
4. traces each change to the exact policies and controls it affects;
5. answers plain-English questions using only cited, approved evidence.

Gemini proposes; people decide. No AI output changes the approved baseline on its own.

## 2. The Technology risk example in one paragraph

A bank prepared its compliance work on the **MAS Consultation Paper P003-2019** (March 2019 draft of the Technology Risk Management Guidelines). It interpreted 34 obligations in three areas: Access Control (chapter 9), Cyber Security Assessment (chapter 13) and API Development (section 6.4). It then linked them to 11 policies, 13 controls and risk context, for **102 approved mappings** in total. On 18 January 2021 MAS issued the **final Guidelines**. Compared paragraph by paragraph:

| Result | Obligations | What happens to the earlier work |
|---|---|---|
| Unchanged | 19 | Their 57 mappings can be carried forward with one specialist acknowledgement |
| Modified | 14 | Their 45 mappings get individual re-review |
| Removed | 1 (6.4.2) | Flagged for retirement review; nothing is deleted automatically |
| New | 2 (6.1.3, 6.1.4) | Mapped from scratch; missing controls are shown as gaps |

Result: **45 of 102 mappings need review instead of 102, a 54.9% reduction computed from the data.** A three-word change ("is encouraged to" → "should", paragraph 13.4.1) is still caught.

Regulatory text comes from the two official MAS PDFs. The bank's policies and controls are synthetic demonstration data.

## 3. Screen layout and controls

### Top bar

| Control | What it does |
|---|---|
| **Text size** (A− · 100% · A+) | Enlarges all text in four steps (100%, 113%, 125%, 138%). Click the percentage to return to 100%. Your choice is remembered in this browser. |
| **Regulation** | Switches between the two worked examples: **Technology risk · 2021 final** and **Marketing rules · 2023 proposal**. Switching returns you to Overview. |
| **Demo reviewer role** | Chooses who you are acting as: **Regulatory Specialist** (avatar RS, teal), **Policy Owner** (PO, amber) or **Risk Steward** (RK, blue). A strip at the top of every page says what the current role can decide. Each decision needs a specific role (see section 5): with the wrong role, its button stays disabled and names the role to switch to. Viewing pages is the same for every role. This demonstrates authorization; it is not a login. |

Below the top bar, the strip **CURATED BASELINE · GOLDEN LABELS** reminds you that the starting data is reviewed demonstration data. Live Gemini runs appear in **Workflow runs** and **Ask RegImpact**. **Reset demo** (right) clears the decisions and runs in your current session. The approved baseline is never changed.

### Left navigation

| Page | Use it to |
|---|---|
| **Overview** | See the scenario, headline numbers and what needs attention |
| **Change analysis** | Compare each obligation's draft and final text and confirm the change |
| **Delta Review** | Reuse what is safe and work through the individual re-reviews |
| **Impact lineage** | Follow a change to the policies and controls it affects |
| **Coverage gaps** | See new obligations that have no mapping yet |
| **Mandates & mappings** | Review interpreted obligations and map them to policies |
| **Source register** | Inspect the official documents, fingerprints and extraction |
| **Ask RegImpact** | Ask questions; answers cite approved evidence only |
| **Workflow runs** | Run Gemini workflows and inspect every run's record |

### Sessions

Your decisions are stored in an isolated demonstration session for your browser (four hours by default). Other visitors do not see them, and the approved baseline stays intact. Open a private window for a completely fresh session.

---

## 4. Step-by-step walkthrough (Technology risk · 2021 final)

Follow the steps in order. Each step says which role to select.

### Step 1 — Choose the regulation

1. Open <https://regimpact-ai.web.app>.
2. In the top bar, set **Regulation** to **Technology risk · 2021 final**.
3. Leave **Demo reviewer role** on **Regulatory Specialist**.
4. If you have used the demo before, click **Reset demo** for a clean start.

The amber banner **FINAL GUIDELINES — ISSUED 18 JANUARY 2021** now appears on every page. It reminds you that you are comparing work prepared on the draft with the final rules.

### Step 2 — See how the regulation is loaded (Source register)

This is where a regulation enters the framework.

1. Open **Source register**.
2. Two official MAS documents are listed:

   | Document | ID | Status | Extracted segments |
   |---|---|---|---|
   | Consultation Paper P003-2019 (7 March 2019) | `MAS-TRM-CP-2019` | proposed | 443 |
   | Technology Risk Management Guidelines (18 January 2021) | `MAS-TRM-2021` | in force | 430 |

3. Each card shows **extracted complete**, the **SHA-256** fingerprint of the downloaded PDF, the extraction time and the segment count.
4. **Open official source** opens the document on the MAS website.
5. **Ingest downloaded document** re-runs extraction on the stored PDF and shows a completion message.

How loading works behind the screen:

1. The official PDF is downloaded from `www.mas.gov.sg`. Only declared MAS addresses are accepted.
2. Its SHA-256 fingerprint is recorded. A changed file is rejected until someone reviews it.
3. The text is split into page- and paragraph-anchored segments, which become the evidence every later step quotes.
4. The original and the extracted segments are stored in Google Cloud Storage. Change analysis then compares each obligation's draft paragraph with its final paragraph, using verbatim excerpts.

Extraction proves the text was read correctly. It does not establish legal status or replace a specialist's interpretation.

### Step 3 — Get the overview

1. Open **Overview**.
2. The **Review reduction** card shows **54.9% Estimated**. This is the potential saving before a specialist confirms it. It is based on 102 existing mappings; new obligations are excluded.
3. The four figures underneath show:
   - **102** existing approved mappings;
   - **57** carry-forward candidates, which must pass all safety checks;
   - **45** individual re-reviews;
   - **2** new obligations, assessed separately from reuse.
4. The **scenario guide** (served from Firestore in the hosted app) describes both versions. Its five buttons jump to each part of the story: **1. See the two official texts**, **2. Reuse what still holds**, **3. A quiet but material change**, **4. Trace affected controls** and **5. Ask Gemini with evidence**.
5. **What needs your attention** lists the most important changes first: the two new obligations, then the modified ones with controls to review. Click a card to open it, or click **Explore lineage**.

### Step 4 — Review the interpreted obligations (Mandates & mappings)

Each obligation the bank interpreted from the draft is a **mandate**.

1. Open **Mandates & mappings**. You see all 34 mandates (for example `M-TRM-9-1-1`), each labelled **MODIFIED** or **UNCHANGED** with a short note on what changed.
2. Click **Review mandate and candidates** on any mandate. You will see:
   - the interpretation and its evidence references;
   - risk context (for example **Cyber risk**), which never expands control impact;
   - the **policy candidates** found by hybrid search, with each candidate's vector, keyword and combined (reciprocal rank fusion) rank.
3. To record a prospective mapping, switch the role to **Policy Owner**, pick a candidate, write a rationale and approve or reject it. This creates a scenario mapping in your session only.

### Step 5 — Compare draft and final text (Change analysis)

1. Open **Change analysis**. Each of the 36 changes has a card with its label (**MODIFIED**, **UNCHANGED**, **NEW**, **REMOVED**), a one-line explanation and how many controls it touches.
2. Open **13.4.1 Consider adversarial attack simulation exercises**:
   - **Prepared on the draft** shows the March 2019 text (page 50): "The FI *is encouraged to* perform an adversarial attack simulation exercise…".
   - **Final guideline** shows the January 2021 text (page 47): "The FI *should* perform…".
   - Both are **Verified excerpts** extracted from the official PDFs, with a link to the public MAS source.
   - The tags **MODIFIED** and **strengthened** explain why this obligation needs re-review.
3. Under **Confirm the change effect** (role **Regulatory Specialist**):
   1. keep **Modified** as the classification;
   2. write a rationale of at least a sentence, for example: "Reviewed both excerpts; the obligation moves from optional to expected practice";
   3. tick the evidence-review checkbox;
   4. click **Confirm change effect**.

   The decision is recorded with your role and rationale. An "Unchanged" classification can never override the reuse safeguards.
4. Below, **Interpretation to review** shows the mandate (`M-TRM-13-4-1`) and its risk context. **Review policy candidates** opens the mapping view, and **Explore impact lineage** jumps to Step 8.
5. Compare other kinds of change:
   - **9.1.3 Log user access activity under unique identities** is **UNCHANGED**: only "For accountability" became "For proper accountability".
   - **9.1.4 Enforce a strong password policy** is **UNCHANGED**: the text is identical word for word.
   - **6.4.2 Control access to designated API services** is **REMOVED**: the paragraph is not in the final text, so its mappings are flagged for retirement review.
   - **6.1.3 Govern third-party and open-source code before use** is **NEW**: there is no draft paragraph to compare.

### Step 6 — Run Gemini live on the change (Workflow runs)

1. Open **Workflow runs**.
2. Under **Run a bounded workflow**, choose **Workflow: Classify the change effect (Gemini)** and **Scenario change: 13.4.1 Consider adversarial attack simulation exercises**.
3. Click **Run workflow** and wait for the result (usually 10 to 30 seconds).
4. The run appears in **Run history**. Check:
   - status **SUCCEEDED**, with validation passed;
   - the model (`gemini-3.5-flash`), prompt version and duration;
   - **Inspect structured output**: classification **MODIFIED**, the reason, and the exact quotes from both versions.

   Quotes that do not match the official text are removed by validation; the model cannot invent evidence.
5. To accept or correct the AI's proposal, open **Review this AI recommendation** on the run, with the required role (**Regulatory Specialist** for change effect). Approve, reject or modify it with a rationale. Edited output is validated again.

Other workflows on this page:

| Workflow | What it proposes | Reviewer |
|---|---|---|
| Classify the change effect (Gemini) | Change classification and whether the change affects existing mappings | Regulatory Specialist |
| Recommend a policy mapping from hybrid search (Gemini) | The best policies from the hybrid-search candidates | Policy Owner |
| Suggest a risk classification (Gemini) | Risk type and driver from the allowed taxonomy | Risk Steward |
| Explain control impact from approved paths (Gemini) | A plain-English explanation built only from approved paths | Policy Owner |

The hosted app limits AI usage to 20 operations per minute and 400 per day, shared by all visitors. A run that fails, for example because the model is busy, is kept as a failure; it is never replaced by a cached answer.

### Step 7 — Reuse what still holds (Delta Review)

1. Open **Delta Review**.
2. **Review reduction** shows **54.9% Estimated**.
3. **Safe carry-forward** shows **57 candidates**. These are mappings whose obligations' new text has no effect on them. Reuse requires all four safeguards:
   1. no targeted change statement;
   2. no instrument-wide scope or legal-force change;
   3. a supported "no effect" check;
   4. specialist confirmation.
4. With role **Regulatory Specialist**, click **Acknowledge safe candidates**. The 57 mappings are carried forward and the figure becomes **54.9% Confirmed**. Only a Regulatory Specialist can do this; other roles see a reminder to switch.
5. **Prospective mapping review** lists the remaining **45** mappings, with a counter ("0 of 45 individual re-reviews completed"). Each row shows the mandate, the target (policy, risk type or risk driver), the change label and its status (**re review required**).
6. Click **Review mapping** on a row:
   - read the proposed scenario treatment and the reason;
   - switch to the role named in the dialog (**Policy Owner** for policies, **Risk Steward** for risk targets);
   - write a rationale of at least 10 characters;
   - click **Approve scenario mapping** or **Reject**.

   The dialog states that the decision does not amend the current policy, control or regulatory baseline.
7. If a change is still unresolved, the dialog asks you to **Confirm change effect first** and links to the mandate review.
8. Recorded rows change to **Review decision** and are read-only. **Reset demo** lets you rehearse again.

### Step 8 — Follow the impact to controls (Impact lineage)

1. Open **Impact lineage** (or click **View impact** on Delta Review).
2. Pick a change from the buttons at the top, for example **13.4.1** or **9.1.1 Apply never-alone, segregation of duties and least privilege**.
3. Read the path: **01 / Mandate → 02 / Policy requirement → 03 / Control objective**. For 9.1.1, the path is `M-TRM-9-1-1` → `PR-TRM-UAM` User access management → `CO-TRM-UAM-01` Quarterly user access recertification and `CO-TRM-UAM-02` Joiner-mover-leaver access revocation. Both controls are marked **Review needed**.
4. Use the view controls:
   - **Approved baseline relationships only** (on by default). Untick it to include mappings you approved in this session.
   - **Impacted controls only**, and **Focus an impacted control**, narrow the drawing. Filters never change the review totals.
   - **Expand source and provision context** shows the draft and final evidence one level upstream.
5. Under **Inspect a relationship**, click any link (for example `PR-TRM-UAM → CO-TRM-UAM-01`). **Explain this relationship** shows why the link exists: evidence, origin (approved baseline or enterprise catalog), reviewer and model/retrieval provenance where available. To have Gemini explain a change's impact from the approved paths, run **Explain control impact from approved paths (Gemini)** in Workflow runs.
6. **Controls to review** lists every affected control under the final rules.
7. **Authorize control impact** (role **Policy Owner**): click **Review control impact** for a control, then confirm, reject or modify its scope, give a rationale and save. The record keeps the reviewer, time, previous and final scope. Confirming impact records an assessment; it does not claim the control is effective.

Risk tags such as **Cyber risk** and **Excessive or stale access** appear as context only. They never add controls to the impact.

### Step 9 — Close the gaps for new rules (Coverage gaps)

1. Open **Coverage gaps**. The two **New final obligations** are listed:
   - **6.1.3 Govern third-party and open-source code before use**;
   - **6.1.4 Track vulnerabilities in third-party and open-source code**.
2. New obligations are never absorbed into the approved graph silently. Click **Review policy candidates** to see hybrid-search candidates, then, as **Policy Owner**, approve a prospective mapping with a rationale.
3. Click **Inspect coverage and lineage** to see the result. A policy without an approved policy-to-control path remains a visible **control gap**: approving a policy does not invent a control.

### Step 10 — Ask in plain English (Ask RegImpact)

1. Open **Ask RegImpact**.
2. Click a suggested question or type your own:
   - "Which access control obligations changed in the final guidelines, and which controls should we review?"
   - "Why does the adversarial attack simulation obligation need review?"
   - "Where are the coverage gaps for the new open-source code obligations?"
3. Click **Ask RegImpact**. In the hosted app, a read-only Gemini agent (built with Google's Agent Development Kit) retrieves facts with tools. Model Armor screens the question and the answer. Every reference is checked against the evidence retrieved in this run before the answer is shown.
4. Inspect the answer: its verified-reference count, the supporting sources (cards), the tool activity and the run/model identity.

Ask cannot approve or change anything. It answers from the approved baseline graph, so to see mappings you approved in this session, use Impact lineage with scenario relationships included.

### Step 11 — Check the audit trail (Workflow runs)

Open **Workflow runs** again. **Run history** lists every model, retrieval and Ask run in your session, with status, validation, duration and model identity. Expand a run to inspect its structured output and its human review, if any.

### Step 12 — Start again

Click **Reset demo** to clear your session's decisions and runs. The approved baseline, the official documents and the shared AI budget are not affected.

---

## 5. Who can do what (demo roles)

| Action | Role |
|---|---|
| Confirm a change effect; review change-effect runs | Regulatory Specialist |
| Acknowledge safe carry-forward candidates | Regulatory Specialist |
| Approve or reject prospective policy mappings; review policy-map and impact-explain runs | Policy Owner |
| Authorize control impact | Policy Owner |
| Review risk mappings and risk-classification runs | Risk Steward |

If a button is disabled, check the message next to it; it names the role you need.

## 6. Feature reference

| Feature | Where | Notes |
|---|---|---|
| Official source ingestion with SHA-256 fingerprints | Source register | Page and paragraph anchors; Cloud Storage originals |
| Verified excerpts, draft vs final | Change analysis | Verbatim text with page numbers and source links |
| Change classification (Unchanged, Modified, New, Removed) | Change analysis, Workflow runs | Gemini proposes, a specialist confirms |
| Safe carry-forward with four safeguards | Delta Review | One bulk acknowledgement; computed reduction |
| Individual mapping re-review | Delta Review | Role-gated approve or reject with rationale |
| Graph lineage: mandate → policy → control | Impact lineage | Spanner Graph traversal of approved paths |
| Explain this relationship | Impact lineage | Evidence and provenance for each relationship |
| Control-impact authorization | Impact lineage | Confirm, reject or modify scope |
| Hybrid policy search (vector + keyword + rank fusion) | Mandates & mappings, Coverage gaps | Shows each candidate's ranks |
| Coverage gaps for new obligations | Coverage gaps | Gaps stay visible until mapped |
| Grounded Q&A agent | Ask RegImpact | Read-only, Model Armor screening, verified references |
| Run provenance and human review | Workflow runs | Model, prompt version, validation, timing |
| Scenario guide | Overview | Served from Firestore in the hosted app |
| Text size control | Top bar | 100% to 138%, remembered per browser |
| Regulation selector | Top bar | Two worked MAS examples |
| Session reset | Top bar strip | Clears only your session |

## 7. Statuses and what to do

| You see | Meaning and action |
|---|---|
| **Estimated** vs **Confirmed** reduction | Estimated until a Regulatory Specialist acknowledges the safe candidates |
| **re review required** | The mapping's obligation changed; review it individually |
| **carry forward pending ack** | Eligible for reuse once acknowledged |
| **Confirm change effect first** | The change is unresolved; confirm its classification on the mandate review |
| `AI_RATE_LIMIT` | The shared AI budget is used up for now; wait and retry |
| `MANUAL_REVIEW_REQUIRED` / validation failed | The model output did not pass checks; inspect the messages. Nothing is accepted automatically |
| Model busy (429) | The run is recorded as failed; retry later. Cached output is never shown as a live result |
| Role reminder under a button | Switch **Demo reviewer role** as shown |
| Decision is read-only | Already recorded; use **Reset demo** to rehearse again |
| `SOURCE_PDF_UNAVAILABLE` | The registered PDF is not in storage; an operator must stage it (section 9) |

## 8. The second example: Marketing rules · 2023 proposal (the safety net)

Switch **Regulation** to **Marketing rules · 2023 proposal**. This compares the MAS marketing and distribution guideline (FSG-G02, 2016) with the 2023 consultation proposal. One safeguard keeps its exact wording, but the proposal would make the safeguards binding for investment products. RegImpact therefore holds **all 6 mappings for review and reuses none**. This shows that reuse is blocked when legal weight changes, even if the words do not. The proposal is presented as a historical proposal, never as current law.

## 9. Adding a new regulation (operator process)

The browser cannot upload arbitrary PDFs or create a new scenario. Adding a regulation is an operator and data-curation task:

1. **Register the sources.** Add each official document version to a scenario source manifest under `data/public/` (for example `trm-source-manifest.json`), with a unique ID, title, date, official URL, legal status and expected SHA-256. Download the PDFs into `data/public/downloads/`; they are not committed.
2. **Extract and store.** Ingest each source through the source service (locally, or into the private Cloud Storage bucket for the hosted app). Then check **extracted complete** and the segment count in **Source register**.
3. **Build the scenario data.** Follow `backend/scripts/build_trm_seed.py`. Define the interpreted mandates with verbatim evidence from both versions, the change labels, and the synthetic or authorized enterprise policies, controls and approved relationships. The script writes the seed bundle, the catalog and the scenario guide.
4. **Register the scenario.** Add a `ScenarioSpec` to `backend/app/config/scenarios.py` with its key, scenario ID, data files, label and source note. List its key in the `scenarios` setting. The **Regulation** selector picks it up automatically.
5. **Validate locally.** Run the backend in local mode (`REGIMPACT_MODE=local`) and run the test suite. Then walk through this guide on the new scenario.
6. **Load the cloud data.** Use `scripts/spanner_admin.py --scenario-id <ID>`: run `plan` first, then `import-seed`, `index-lexical` and `index-embeddings`. Import is insert-only, and embedding generation is billable. Load the scenario guide into Firestore under `demo_catalog/<scenario ID>`.
7. **Release.** Push to `main`. CI runs backend and frontend checks, then a keyless deploy that verifies a no-traffic candidate before switching traffic. Have a specialist validate the new example before presenting it.

## 10. Release pipeline (summary)

Pushing to `main` on GitHub runs **CI and deployment**. It runs backend lint, tests, contract and secret checks, plus frontend lint, type checks, tests and build. On success, Cloud Build creates an image. A Cloud Run candidate is verified with no production traffic, then Cloud Run and Firebase Hosting are published together. A failed release rolls back automatically. The deck and video are restored from a private, hash-checked Cloud Storage bundle, so code releases never overwrite them.
