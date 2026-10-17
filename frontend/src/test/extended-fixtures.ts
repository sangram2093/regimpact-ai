import type { ChangeDetail } from '../types/api';
import type {
  AskConfig,
  AskResponse,
  MandateRecord,
  PolicyCandidates,
  SourcesResponse,
  WorkflowRun,
} from '../types/workflows';
import { dashboard, edge } from './fixtures';

export const localRun: WorkflowRun = {
  id: 'RUN-LOCAL-1',
  workflow: 'policy-map',
  kind: 'LOCAL_DETERMINISTIC',
  status: 'SUCCEEDED',
  model: null,
  prompt_version: null,
  started_at: '2026-10-17T10:00:00Z',
  duration_ms: 12,
  label: 'Deterministic lexical retrieval — no live AI',
  validation_status: 'PASSED',
  steps: [
    {
      name: 'retrieve_candidates',
      status: 'SUCCEEDED',
      detail: 'Ranked known synthetic policy IDs.',
    },
  ],
};
export const sourceRecords: SourcesResponse = {
  sources: [
    {
      id: 'MAS-2016',
      title: 'Public MAS baseline guidelines',
      source_url: 'https://www.mas.gov.sg/',
      regulator: 'MAS',
      publication_date: '2016-12-23',
      legal_status: 'GUIDANCE',
      ingestion_status: 'PDF_UNAVAILABLE',
      sha256: null,
      segment_count: 0,
      retrieved_at: null,
      verification_note: 'Source artifact unavailable; paraphrases remain explicitly labelled.',
      can_ingest: false,
    },
  ],
  disclosures: ['Public source documents and synthetic enterprise catalogs are kept separate.'],
};
export const changeDetail: ChangeDetail = {
  ...dashboard.changes[0],
  baseline_evidence: [{ ...edge.evidence[0], id: 'EV-BASE' }],
  proposal_evidence: [{ ...edge.evidence[0], id: 'EV-PROPOSAL' }],
  mandate: { id: 'M-GIFT', title: 'Gift safeguard' },
  risk_tags: ['Conduct risk'],
  proposal_notice: 'Proposed — not an in-force requirement',
};
export const mandate: MandateRecord = {
  id: 'M-GIFT',
  title: 'Gift safeguard',
  text: 'Review the prospective gift scope against approved enterprise policies.',
  status: 'PROPOSED',
  source_id: 'MAS-2016',
  change_id: 'CHANGE-GIFT',
  classification: 'MODIFIED',
  review_status: 'CLASSIFICATION_CONFIRMED',
  evidence: changeDetail.proposal_evidence,
  reviewed_by: 'Demo reviewer',
  rationale: 'Scope changed.',
  classification_confirmed: true,
};
export const policyCandidates: PolicyCandidates = {
  mandate_id: 'M-GIFT',
  candidates: [
    {
      id: 'PR-GIFT-01',
      title: 'Gift approval policy',
      text: 'Synthetic policy for prospecting gift approval.',
      vector_rank: null,
      lexical_rank: 1,
      rrf_rank: 1,
      rrf_score: 0.01639,
      reason: 'Lexical overlap with prospecting and gifts.',
    },
  ],
  run: localRun,
  review_status: 'PENDING_REVIEW',
  selected_policy_id: null,
  mapping_allowed: true,
  mapping_block_reason: null,
};
export const askConfig: AskConfig = {
  mode: 'local',
  label: 'Deterministic graph answer — no live AI',
  suggested_questions: [
    'Which controls are linked to the gift safeguard?',
    'Where are the coverage gaps?',
  ],
  available: true,
  reason: null,
};
export const askResponse: AskResponse = {
  answer:
    'The approved baseline links the gift mandate [M-GIFT] to gift review [CO-GIFT-01]. Proposed scope still needs review.',
  grounded: true,
  verified_references: 2,
  total_references: 2,
  citations: [
    {
      id: 'M-GIFT',
      label: 'Gift safeguard',
      type: 'MANDATE',
      excerpt: 'Baseline gift safeguard interpretation.',
      source_url: 'https://www.mas.gov.sg/',
    },
    {
      id: 'CO-GIFT-01',
      label: 'Gift review control',
      type: 'CONTROL',
      excerpt: 'Synthetic enterprise gift review.',
      source_url: null,
    },
  ],
  tool_calls: [
    {
      name: 'get_change_impact',
      status: 'SUCCEEDED',
      summary: 'Retrieved approved compliance paths.',
    },
  ],
  run: {
    ...localRun,
    id: 'RUN-ASK-1',
    workflow: 'ask',
    label: 'Deterministic graph answer — no live AI',
  },
};
