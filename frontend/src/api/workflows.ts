import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';
import { request } from './client';
import type { ChangeDetail } from '../types/api';
import type {
  AskConfig,
  AskResponse,
  ClassificationInput,
  MandateRecord,
  PolicyCandidates,
  PolicyMappingInput,
  SourceRecord,
  SourcesResponse,
  WorkflowKind,
  WorkflowRun,
  WorkflowResult,
  WorkflowOutputReviewInput,
  ControlImpactAssessment,
  ControlImpactReviewInput,
  ImpactAssessmentList,
} from '../types/workflows';

export const sourcesQuery = queryOptions({
  queryKey: ['sources'],
  queryFn: () => request<SourcesResponse>('/sources'),
});
export const mandatesQuery = queryOptions({
  queryKey: ['mandates'],
  queryFn: () => request<{ mandates: MandateRecord[] }>('/mandates'),
});
export const candidatesQuery = (id: string) =>
  queryOptions({
    queryKey: ['candidates', id],
    queryFn: () =>
      request<PolicyCandidates>(`/mandates/${encodeURIComponent(id)}/policy-candidates`),
    enabled: Boolean(id),
  });
export const runsQuery = queryOptions({
  queryKey: ['workflow-runs'],
  queryFn: () => request<{ runs: WorkflowRun[] }>('/workflows/runs'),
});
export const runDetailQuery = (id: string) =>
  queryOptions({
    queryKey: ['workflow-run', id],
    queryFn: () => request<WorkflowResult>(`/workflows/runs/${encodeURIComponent(id)}`),
  });
export const askConfigQuery = queryOptions({
  queryKey: ['ask-config'],
  queryFn: () => request<AskConfig>('/ask/config'),
});
export const impactAssessmentsQuery = (id: string) =>
  queryOptions({
    queryKey: ['impact-assessments', id],
    queryFn: () =>
      request<ImpactAssessmentList>(`/changes/${encodeURIComponent(id)}/impact-assessments`),
    enabled: Boolean(id),
  });

export function useIngestSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      request<SourceRecord>(`/sources/${encodeURIComponent(id)}/ingest`, {}),
    onSuccess: () => client.invalidateQueries(),
  });
}
export function useClassification() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: ClassificationInput & { id: string }) =>
      request<ChangeDetail>(`/changes/${encodeURIComponent(id)}/classify`, input),
    onSuccess: () => client.invalidateQueries(),
  });
}
export function usePolicyMapping() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: PolicyMappingInput & { id: string }) =>
      request<PolicyCandidates>(`/mandates/${encodeURIComponent(id)}/policy-mapping`, input),
    onSuccess: () => client.invalidateQueries(),
  });
}
export function useAsk() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { question: string; scenario_id: string }) =>
      request<AskResponse>('/ask', input),
    onSuccess: () => client.invalidateQueries({ queryKey: ['workflow-runs'] }),
  });
}
export function useWorkflowRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      kind,
      ...input
    }: {
      kind: WorkflowKind;
      mandate_id?: string;
      change_id?: string;
    }) => request<WorkflowRun>(`/workflows/${kind}/run`, input),
    onSuccess: () => client.invalidateQueries(),
  });
}

export function useWorkflowOutputReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: WorkflowOutputReviewInput & { id: string }) =>
      request<WorkflowResult>(`/workflows/runs/${encodeURIComponent(id)}/review`, input),
    onSuccess: () => client.invalidateQueries(),
  });
}
export function useControlImpactReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: ControlImpactReviewInput & { id: string }) =>
      request<ControlImpactAssessment>(
        `/impact-assessments/${encodeURIComponent(id)}/review`,
        input,
      ),
    onSuccess: () => client.invalidateQueries(),
  });
}
