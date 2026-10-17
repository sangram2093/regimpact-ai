import { ArrowDownRight, CircleHelp, ShieldCheck } from 'lucide-react';
import type { Metrics } from '../../types/api';
import { Badge } from '../../components/Primitives';

const percent = (value: number) =>
  new Intl.NumberFormat('en', { maximumFractionDigits: 1 }).format(value);

export function ReviewMetric({
  metrics,
  compact = false,
}: {
  metrics: Metrics;
  compact?: boolean;
}) {
  const confirmed = metrics.review_reduction !== null;
  const value = confirmed ? metrics.review_reduction : metrics.estimated_review_reduction;
  // With no safe candidate, the useful result is how much unsafe reuse was blocked,
  // not a headline 0% saving. The reduction stays visible below as the same computed value.
  const safetyNet = metrics.carry_forward_candidates === 0 && metrics.existing_mapping_items > 0;
  if (safetyNet) {
    return (
      <section
        className={`review-metric safety-net ${compact ? 'metric-compact' : ''}`}
        aria-label="Delta Review result"
      >
        <div className="metric-heading">
          <span>
            <ShieldCheck size={18} />
            Delta Review result
          </span>
          <Badge tone="amber">Safety net engaged</Badge>
        </div>
        <div className="metric-value">
          {metrics.individual_rechecks}
          <span>/{metrics.existing_mapping_items}</span>
        </div>
        <p>
          approved mappings routed to individual review. 0 silent carry-forwards: the proposed
          binding treatment and new telemarketing scope block reuse, even where wording is
          unchanged.
        </p>
        <div className="metric-formula">
          <CircleHelp size={14} />
          <span>
            Review reduction {value === null ? '—' : `${percent(value)}%`} (estimated) · based on{' '}
            {metrics.existing_mapping_items} existing mappings; new obligations excluded.
          </span>
        </div>
      </section>
    );
  }
  return (
    <section
      className={`review-metric ${compact ? 'metric-compact' : ''}`}
      aria-label="Review reduction"
    >
      <div className="metric-heading">
        <span>
          <ArrowDownRight size={18} />
          Review reduction
        </span>
        <Badge tone="teal">{confirmed ? 'Confirmed' : 'Estimated'}</Badge>
      </div>
      <div className="metric-value">
        {value === null ? '—' : percent(value)}
        {value !== null && <span>%</span>}
      </div>
      <p>
        {confirmed
          ? 'Safe reuse acknowledged by a specialist.'
          : 'Potential saving, subject to specialist acknowledgement.'}
      </p>
      <div className="metric-formula">
        <CircleHelp size={14} />
        <span>
          Based on {metrics.existing_mapping_items} existing mappings; new obligations excluded.
        </span>
      </div>
    </section>
  );
}
