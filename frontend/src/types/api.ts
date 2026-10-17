export interface Envelope<T> {
  data: T;
  meta: { request_id: string; mode?: string; data_origin?: string };
}
export interface Metrics {
  existing_mapping_items: number;
  carry_forward_candidates: number;
  acknowledged_mappings: number;
  individual_rechecks: number;
  completed_rechecks: number;
  unresolved_items: number;
  bulk_ack_actions: number;
  estimated_review_reduction: number | null;
  review_reduction: number | null;
  carry_forward_rate: number | null;
  new_obligations: number;
}
export interface Scenario {
  id: string;
  title: string;
  regulator: string;
  baseline_label: string;
  proposal_label: string;
  status: string;
  proposal_notice: string;
}
export interface Change {
  id: string;
  title: string;
  classification: string;
  change_nature: string[];
  summary: string;
  mandate_id: string;
  impacted_controls: number;
  review_status: string;
  is_proposal: boolean;
}
export interface Dashboard {
  scenario: Scenario;
  metrics: Metrics;
  changes: Change[];
  impact_summary: Record<string, unknown>;
  run: {
    id: string;
    kind: string;
    status: string;
    model: string | null;
    timestamp: string | null;
    duration_ms: number | null;
    label: string;
  };
}
export interface Evidence {
  id: string;
  source_id: string;
  title: string;
  source_url: string;
  paragraph_ref: string;
  page: number | null;
  text: string;
  text_kind: 'VERIFIED_EXCERPT' | 'PARAPHRASE';
  verification_status: string;
  data_origin: string;
}
export interface ChangeDetail extends Change {
  baseline_evidence: Evidence[];
  proposal_evidence: Evidence[];
  mandate: { id: string; title: string };
  risk_tags: string[];
  proposal_notice: string;
  classification_review?: {
    classification: string;
    reviewer: string;
    rationale: string;
    reviewed_at: string;
  } | null;
}
export interface Assessment {
  id: string;
  baseline_edge_id: string | null;
  mandate_id: string;
  mandate_title: string;
  target_id: string | null;
  target_label: string | null;
  classification: string;
  status: string;
  recommendation: string;
  reason: string;
  eligible_for_carry_forward: boolean;
  reviewed_by: string | null;
  rationale: string | null;
  required_role: 'Policy Owner' | 'Risk Steward';
  relationship: string;
}
export interface DeltaReview {
  scenario_id: string;
  metrics: Metrics;
  assessments: Assessment[];
}
export interface Impact {
  nodes: { id: string; label: string; type: string; status: string }[];
  edges: { id: string; source: string; target: string; label: string; status: string }[];
  controls: { id: string; title: string; impact_type: string }[];
  coverage: 'COMPLETE' | 'PARTIAL' | 'NO_POLICY_MAPPING';
  risk_tags: string[];
}
export interface EdgeExplanation {
  id: string;
  source_id: string;
  target_id: string;
  relationship: string;
  status: string;
  evidence: Evidence[];
  data_origin: string;
  provenance: {
    proposed_by: string;
    decision_source: string;
    model: string | null;
    prompt_version: string | null;
    reviewer: string | null;
    reviewed_at: string | null;
    vector_rank: number | null;
    lexical_rank: number | null;
    rrf_rank: number | null;
    rrf_score: number | null;
    reason: string;
    alternative: string | null;
    alternative_reason: string | null;
  };
}
export type ReviewerRole = 'Regulatory Specialist' | 'Policy Owner' | 'Risk Steward';
export interface ReviewInput {
  decision: 'APPROVE' | 'REJECT';
  reviewer: string;
  role: ReviewerRole;
  rationale: string;
}
