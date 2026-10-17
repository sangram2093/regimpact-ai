import type { Evidence, ReviewerRole } from './api';

export interface WorkflowRun {
  id: string;
  workflow: string;
  kind: 'LOCAL_DETERMINISTIC' | 'LIVE_AI' | 'SEED';
  status: string;
  model: string | null;
  prompt_version: string | null;
  started_at: string | null;
  duration_ms: number | null;
  label: string;
  validation_status: string;
  steps: { name: string; status: string; detail: string }[];
}
export interface SourceRecord {
  id: string;
  title: string;
  source_url: string;
  regulator: string;
  publication_date: string;
  legal_status: string;
  ingestion_status: string;
  sha256: string | null;
  segment_count: number;
  retrieved_at: string | null;
  verification_note: string;
  can_ingest?: boolean;
}
export interface SourcesResponse {
  sources: SourceRecord[];
  disclosures: string[];
}
export interface MandateRecord {
  id: string;
  title: string;
  text: string;
  status: string;
  source_id: string;
  change_id: string;
  classification: string;
  review_status: string;
  evidence: Evidence[];
  reviewed_by: string | null;
  rationale: string | null;
  classification_confirmed?: boolean;
}
export interface PolicyCandidate {
  id: string;
  title: string;
  text: string;
  vector_rank: number | null;
  lexical_rank: number | null;
  rrf_rank: number | null;
  rrf_score: number | null;
  reason: string;
}
export interface PolicyCandidates {
  mandate_id: string;
  candidates: PolicyCandidate[];
  run: WorkflowRun;
  review_status: string;
  selected_policy_id: string | null;
  rationale?: string | null;
  reviewed_by?: string | null;
  mapping_allowed?: boolean;
  mapping_block_reason?: string | null;
}
export interface WorkflowResult {
  run: WorkflowRun;
  output: unknown;
  status: string;
  validation_errors: string[];
  review?: WorkflowOutputDecision | null;
  required_role?: ReviewerRole | null;
  review_allowed?: boolean;
  block_reason?: string | null;
}
export interface WorkflowOutputDecision {
  decision: 'APPROVE' | 'REJECT' | 'MODIFY';
  reviewer: string;
  role: ReviewerRole;
  rationale: string;
  reviewed_at: string;
  previous_output: unknown;
  final_output: unknown;
}
export interface WorkflowOutputReviewInput {
  decision: 'APPROVE' | 'REJECT' | 'MODIFY';
  reviewer: string;
  role: ReviewerRole;
  rationale: string;
  final_output?: Record<string, unknown>;
}
export interface ControlImpactAssessment {
  id: string;
  change_id: string;
  control_id: string;
  title: string;
  status: 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'MODIFIED';
  impact_type: string;
  scope_note: string;
  review: WorkflowOutputDecision | null;
}
export interface ImpactAssessmentList {
  assessments: ControlImpactAssessment[];
  required_role: 'Policy Owner';
}
export interface ControlImpactReviewInput {
  decision: 'APPROVE' | 'REJECT' | 'MODIFY';
  reviewer: string;
  role: ReviewerRole;
  rationale: string;
  scope_note?: string;
}
export interface ClassificationInput {
  classification: 'MODIFIED' | 'UNCHANGED' | 'NEW' | 'REMOVED';
  reviewer: string;
  role: ReviewerRole;
  rationale: string;
  evidence_ids: string[];
}
export interface PolicyMappingInput {
  policy_id: string;
  decision: 'APPROVE' | 'REJECT';
  rationale: string;
  reviewer: string;
  role: ReviewerRole;
}
export interface AskConfig {
  mode: string;
  label: string;
  suggested_questions: string[];
  available: boolean;
  reason: string | null;
}
export interface AskCitation {
  id: string;
  label: string;
  type: string;
  excerpt: string | null;
  source_url: string | null;
}
export interface AskResponse {
  answer: string;
  grounded: boolean;
  verified_references: number;
  total_references: number;
  citations: AskCitation[];
  tool_calls: { name: string; status: string; summary: string }[];
  run: WorkflowRun;
}
export type WorkflowKind =
  'interpret' | 'risk-map' | 'policy-map' | 'pcs-extract' | 'change-effect' | 'impact-explain';
