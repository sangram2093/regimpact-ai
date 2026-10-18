import { humanize } from '../../utils/format';
import { ArrowRight, Gift, MessageSquareText, UserRoundCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Change } from '../../types/api';
import { Badge } from '../../components/Primitives';
import { useScenarioMode } from '../../hooks/scenario';

export function ChangeCard({ change, index = 0 }: { change: Change; index?: number }) {
  const { copy } = useScenarioMode();
  const Icon = change.id.includes('GIFT')
    ? Gift
    : change.classification === 'NEW'
      ? MessageSquareText
      : UserRoundCheck;
  return (
    <article className="change-card">
      <div className="change-card-top">
        <span
          className={`change-icon ${change.classification === 'NEW' ? 'change-icon-amber' : ''}`}
        >
          <Icon size={21} />
        </span>
        <div className="inline-badges">
          <Badge tone={change.classification === 'UNCHANGED' ? 'teal' : 'amber'}>
            {change.classification}
          </Badge>
          <Badge>{copy.cardBadge}</Badge>
        </div>
      </div>
      <p className="card-kicker">
        CHANGE {String(index + 1).padStart(2, '0')} / {copy.sourceEyebrow}
      </p>
      <h3>
        <Link to={`/changes/${change.id}`}>{change.title}</Link>
      </h3>
      <p className="change-summary">{change.summary}</p>
      <div className="change-card-bottom">
        <span>
          {change.impacted_controls > 0
            ? `${change.impacted_controls} control${change.impacted_controls === 1 ? '' : 's'} to review`
            : 'Mapping coverage to assess'}
        </span>
        <Link
          className="round-link"
          aria-label={`Analyze ${change.title}`}
          to={`/changes/${change.id}`}
        >
          <ArrowRight size={17} />
        </Link>
      </div>
      <span className="card-status">{humanize(change.review_status)}</span>
    </article>
  );
}
