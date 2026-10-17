import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';
import { request } from './client';
import type {
  Assessment,
  ChangeDetail,
  Dashboard,
  DeltaReview,
  EdgeExplanation,
  Impact,
  ReviewInput,
  ReviewerRole,
} from '../types/api';

export const dashboardQuery = queryOptions({
  queryKey: ['dashboard'],
  queryFn: () => request<Dashboard>('/dashboard'),
});
export const changeQuery = (id: string) =>
  queryOptions({
    queryKey: ['change', id],
    queryFn: () => request<ChangeDetail>(`/changes/${encodeURIComponent(id)}`),
  });
export const deltaQuery = (id: string) =>
  queryOptions({
    queryKey: ['delta', id],
    queryFn: () => request<DeltaReview>(`/changes/${encodeURIComponent(id)}/delta-review`),
    enabled: Boolean(id),
  });
export const impactQuery = (id: string, includeScenario = false) =>
  queryOptions({
    queryKey: ['impact', id, includeScenario],
    queryFn: () =>
      request<Impact>(
        `/changes/${encodeURIComponent(id)}/impact${includeScenario ? '?include_scenario=true' : ''}`,
      ),
    enabled: Boolean(id),
  });
export const edgeQuery = (id: string) =>
  queryOptions({
    queryKey: ['edge', id],
    queryFn: () => request<EdgeExplanation>(`/edges/${encodeURIComponent(id)}/explain`),
    enabled: Boolean(id),
  });

export function useAcknowledge(scenarioId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (role: ReviewerRole) =>
      request<DeltaReview>(`/changes/${encodeURIComponent(scenarioId)}/acknowledge-carry-forward`, {
        role,
        reviewer: 'Demo reviewer',
      }),
    onSuccess: () => client.invalidateQueries(),
  });
}
export function useReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: ReviewInput & { id: string }) =>
      request<Assessment>(`/assessments/${encodeURIComponent(id)}/review`, input),
    onSuccess: () => client.invalidateQueries(),
  });
}
export function useReset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => request<{ reset: boolean }>('/demo/reset', {}),
    onSuccess: () => client.invalidateQueries(),
  });
}
