import { humanize } from '../utils/format';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CheckCheck, Info, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { dashboardQuery, deltaQuery, useAcknowledge } from '../api/queries';
import type { Assessment } from '../types/api';
import { useDemo } from '../hooks/demo';
import {
  Badge,
  ErrorState,
  LoadingState,
  PageHeading,
  ProposalBanner,
} from '../components/Primitives';
import { ReviewMetric } from '../features/dashboard/ReviewMetric';
import { ReviewDialog } from '../features/review/ReviewDialog';

export function DeltaReviewPage() {
  const dashboard = useQuery(dashboardQuery);
  const scenarioId = dashboard.data?.scenario.id ?? '';
  const query = useQuery(deltaQuery(scenarioId));
  const acknowledge = useAcknowledge(scenarioId);
  const { role } = useDemo();
  const [selected, setSelected] = useState<Assessment | null>(null);
  if (dashboard.error || query.error)
    return (
      <ErrorState
        error={dashboard.error ?? query.error!}
        retry={() => {
          void dashboard.refetch();
          void query.refetch();
        }}
      />
    );
  if (query.isPending || !dashboard.data)
    return <LoadingState label="Preparing your review queue…" />;
  const { metrics, assessments } = query.data;
  const eligible = metrics.carry_forward_candidates > 0;
  const acknowledged =
    eligible && metrics.acknowledged_mappings >= metrics.carry_forward_candidates;
  return (
    <>
      <PageHeading
        eyebrow="THE CORE WORKFLOW"
        title="Delta Review"
        description="Reuse only what is safe. Give every material change the individual judgment it deserves."
        action={
          <Link className="button button-secondary" to="/impact">
            View impact <ArrowRight size={16} />
          </Link>
        }
      />
      <ProposalBanner />
      <div className="delta-summary page-section">
        <ReviewMetric metrics={metrics} compact />
        <section className="panel carry-forward-panel">
          <div className="panel-header">
            <h2>
              <CheckCheck size={20} />
              Safe carry-forward
            </h2>
            <Badge tone={eligible ? 'teal' : 'amber'}>
              {metrics.carry_forward_candidates} candidates
            </Badge>
          </div>
          <p>
            {eligible
              ? `${metrics.carry_forward_candidates} mappings belong to obligations whose new text has no effect on them, and each passed all four safeguards. One acknowledgement carries them forward; the other ${metrics.individual_rechecks} get individual review.`
              : 'Unsafe reuse blocked. No mapping meets all four carry-forward safeguards: the gift safeguard is directly targeted, and the identity safeguard — whose wording is unchanged — is caught by the proposed binding treatment for investment products. A text diff would have carried it forward silently.'}
          </p>
          <p className="fine-print">
            Reuse needs all four: no targeted change statement, no instrument-wide scope or
            legal-force proposal, a supported no-effect check and specialist confirmation.
          </p>
          <button
            className="button button-primary"
            disabled={
              !eligible || acknowledged || role !== 'Regulatory Specialist' || acknowledge.isPending
            }
            onClick={() => acknowledge.mutate(role)}
          >
            <ShieldCheck size={16} />
            {acknowledged
              ? 'Candidates acknowledged'
              : acknowledge.isPending
                ? 'Acknowledging…'
                : 'Acknowledge safe candidates'}
          </button>
          {eligible && role !== 'Regulatory Specialist' && (
            <p className="role-warning">Switch to Regulatory Specialist to acknowledge.</p>
          )}
          {acknowledge.error && <ErrorState error={acknowledge.error} />}
        </section>
      </div>
      <section className="panel review-table-panel">
        <div className="panel-header">
          <div>
            <h2>Prospective mapping review</h2>
            <p className="muted">
              {metrics.completed_rechecks} of {metrics.individual_rechecks} individual re-reviews
              completed
            </p>
          </div>
          <Badge>Human authorization required</Badge>
        </div>
        <div className="table-scroll">
          <table className="review-table">
            <thead>
              <tr>
                <th>Mandate / target</th>
                <th>Change</th>
                <th>Scenario status</th>
                <th>
                  <span className="sr-only">Action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((assessment) => {
                const decided = Boolean(assessment.reviewed_by);
                const mapped = Boolean(assessment.target_id);
                return (
                  <tr key={assessment.id}>
                    <td>
                      <strong>{assessment.mandate_title}</strong>
                      <span>
                        {assessment.target_id ?? 'No policy mapping'}
                        {assessment.target_label ? ` · ${assessment.target_label}` : ''}
                      </span>
                    </td>
                    <td>
                      <Badge tone={assessment.classification === 'NEW' ? 'amber' : 'neutral'}>
                        {assessment.classification}
                      </Badge>
                    </td>
                    <td>
                      <span className={`status-dot ${decided ? 'status-complete' : ''}`} />
                      {humanize(assessment.status)}
                    </td>
                    <td>
                      {!mapped ? (
                        <Link className="text-link" to="/coverage-gap">
                          Inspect gap <ArrowRight size={14} />
                        </Link>
                      ) : assessment.eligible_for_carry_forward ? (
                        <span className="fine-print">Bulk acknowledgement</span>
                      ) : (
                        <button
                          className="button button-small button-secondary"
                          onClick={() => setSelected(assessment)}
                        >
                          {decided ? 'Review decision' : 'Review mapping'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <div className="callout page-section">
        <Info size={19} />
        <div>
          <strong>How the metric is calculated</strong>
          <p>
            Existing mandate-specific mappings form the denominator. Individual re-reviews and one
            bulk acknowledgement action count as work. New obligations and policy-to-control catalog
            links are excluded. Confirmed reduction appears only after safe reuse is acknowledged.
          </p>
        </div>
      </div>
      {selected && (
        <ReviewDialog key={selected.id} assessment={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
