import { ArrowDownRight, CircleHelp } from 'lucide-react';
import type { Metrics } from '../../types/api';
import { Badge } from '../../components/Primitives';

export function ReviewMetric({
  metrics,
  compact = false,
}: {
  metrics: Metrics;
  compact?: boolean;
}) {
  const confirmed = metrics.review_reduction !== null;
  const value = confirmed ? metrics.review_reduction : metrics.estimated_review_reduction;
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
        {value === null
          ? '—'
          : new Intl.NumberFormat('en', { maximumFractionDigits: 1 }).format(value)}
        {value !== null && <span>%</span>}
      </div>
      <p>
        {metrics.carry_forward_candidates === 0
          ? 'Scope and legal-force changes require fresh judgment.'
          : confirmed
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
