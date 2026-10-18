# RegImpact AI

Regulatory Change-to-Control Intelligence · Team RegNexus AI

**Review only what changed.** RegImpact AI helps compliance teams trace a regulatory revision to the enterprise policies and controls that require human review. Evidence, proposed legal status, mapping rationale and reviewer decisions stay visible.

## Submission links

- **Working prototype:** https://regimpact-ai.web.app
- **2:47 demonstration video:** https://regimpact-ai.web.app/submission/RegImpact_AI_Demo.mp4
- **Pitch deck (PDF):** https://regimpact-ai.web.app/submission/RegImpact_AI_Submission.pdf · [PPTX in the prescribed template](https://regimpact-ai.web.app/submission/RegImpact_AI_Submission.pptx)

## Two worked examples

Use the **Regulation** selector at the top of the app to switch between them.

**1. Technology risk: consultation draft to final rules (reuse).** A bank prepared its interpretation on MAS's March 2019 consultation draft of the Technology Risk Management Guidelines. MAS issued the final Guidelines on 18 January 2021. RegImpact compares 34 prepared obligations (Access Control, Cyber Security Assessment and API Development) paragraph by paragraph with the final text: 19 are unchanged, 14 changed, 1 was removed and 2 are new. The 57 mappings of unchanged obligations pass all four safeguards and are carried forward with one specialist acknowledgement, so only 45 of 102 existing mappings need individual review (54.9% less re-review, computed, not hard-coded). Small wording changes with real effect are still caught: "is encouraged to" became "should" for adversarial attack simulation. Both official PDFs are fingerprinted and stored; excerpts are verbatim.

**2. Marketing safeguards: guideline versus a consultation (safety net).** The example below shows the opposite case.

The complete example uses the official MAS FSG-G02 marketing and distribution guideline (2016) and its 2023 consultation proposal. It is explicitly a historical baseline-versus-proposed-revision scenario, **not a claim that the proposal is current binding law**. A later October 2026 response is recorded separately in the source manifest. Both official PDFs are completely extracted and stored with source hashes; enterprise policies and controls are synthetic demonstration data.

Open **Source register → Change analysis → Delta Review → Impact lineage → Explain Edge → Workflow runs → Ask RegImpact**. In Workflow runs, run **Classify the change effect (Gemini)** for a live, validated classification. In the policy-owner demo role, record a prospective review with a rationale. Reset affects your browser session only.

**What the real MAS example shows:** Delta Review routes all six approved baseline mappings to individual review and carries nothing forward silently. The identity safeguard's wording is unchanged, yet its mappings are held because the proposal would make the safeguards binding for investment products: the false carry-forward a wording-only comparison would make. Reuse requires four safeguards (no targeted change statement, no instrument-wide scope or legal-force proposal, a supported no-effect check and specialist confirmation). One genuinely new obligation, upfront intent and consent, is mapped separately. The app does not fabricate savings or automatically approve model output.

## Google Cloud technology

- **Firebase Hosting:** public HTTPS frontend, SPA routing, caching/security headers and a pinned Cloud Run API rewrite.
- **Firestore:** a real scenario/version registry supplies the dashboard walkthrough through the API; server-side reads use a scoped runtime identity.
- **Cloud Run:** one FastAPI service handles deterministic retrieval, review workflows, bounded AI calls and source ingestion.
- **Gemini on Vertex AI:** `gemini-3.5-flash` provides six structured recommendation workflows and bounded read-only Ask; `gemini-embedding-001` produces retrieval vectors. Model location is `global`.
- **Spanner:** relational evidence and mappings, full-text and exact-vector search, approved graph paths and isolated session state. Reciprocal Rank Fusion runs deterministically in the application.
- **Cloud Storage and Model Armor:** private immutable source artifacts; screened Ask input/output plus exact-run evidence grounding.

Cloud Run, Spanner and Firestore are in Mumbai (`asia-south1`). Global Vertex processing is not an India-only processing guarantee.

## Run locally

Python 3.12 and Node.js 22.12+ are required. Local mode needs no cloud credentials.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c backend/requirements-gcp.lock -e './backend[dev,gcp]'
npm ci --prefix frontend
.\.venv\Scripts\python.exe scripts/dev.py
```

Open http://127.0.0.1:5173. Local mode is explicitly deterministic; it never pretends to run Gemini. Configure cloud mode using `.env.example` and the non-secret infrastructure configuration. Use application-default credentials locally and workload identities in deployment; never add credential JSON or keys to this repository.

## Validation and boundaries

The deployed six structured workflows each have a successful real-model run. Browser Ask passed seven of seven reference checks; hosted two-session isolation, idempotency, reset and immutable-baseline checks passed. Earlier provider errors were retained as failures. These are functional smoke checks, not independent legal-accuracy, uptime or model-quality benchmarks.

Run the quality gates with:

```powershell
.\.venv\Scripts\python.exe scripts/check.py
```

Independent specialist labels and blind quality evaluation remain future work. Demonstration roles are not production SSO. Recommendations require human review, and accepted drafts never silently replace the authoritative baseline. Risk tags do not expand impact paths. This is not legal advice and is not affiliated with MAS.

## Source publication

This repository is a clean source snapshot. It excludes private development history, conversations, master design files, pitch/video binaries, downloaded regulatory PDFs and documentation other than this README. Runtime `.prompt` assets, JSON demonstration data, tests, schema and deployment configuration are included because the application requires them. Submission artifacts are hosted separately.

The repository includes CI configuration; the Actions tab shows actual run status. Availability requires the cloud deployment and its trial resources to remain active throughout evaluation.

## CI and continuous deployment

The [CI and deployment workflow](https://github.com/sangram2093/regimpact-ai/actions) runs backend lint/tests/contracts/secret checks and frontend lint/types/tests/build on pull requests and main pushes. Only successful main pushes or manual main runs may deploy. Pull requests never receive deployment credentials.

The deployment job uses GitHub OIDC and Google Workload Identity Federation, restricted to this repository's numeric identity, owner, main branch and workflow. No service-account key or password is stored in GitHub. A dedicated deployer can stage builds, invoke the scoped builder, update the existing Cloud Run service and publish Hosting; it does not receive runtime database or model permissions directly.

Cloud Build produces an image identified by its digest. The job deploys a candidate with no production traffic, checks GCP mode, real Firestore and complete source evidence, then publishes Cloud Run and its paired Firebase Hosting release. Post-release checks verify deep links, API routing and exact submission-asset hashes. A failed publication attempts to restore the previous Hosting version and Cloud Run traffic. Rollback failures make the job fail for operator attention.

The deck and video are restored from a private, immutable Cloud Storage asset bundle declared in `infra/firebase/submission-assets.json`. Their bytes are hash-checked before and after release, so routine code deployments preserve the submission files without committing documents or video to this repository. Database schema changes, corpus imports and billable AI quality evaluations remain explicit operator actions.

To release a code change, push it to main and inspect the workflow's deployment summary. To rerun the same verified release, use **Actions → CI and deployment → Run workflow → main**. Keep the trial resources active during evaluation.
