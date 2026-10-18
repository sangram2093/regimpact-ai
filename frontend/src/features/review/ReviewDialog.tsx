import { humanize } from '../../utils/format';
import { useState } from 'react';
import { Check, X } from 'lucide-react';
import type { Assessment } from '../../types/api';
import { useReview } from '../../api/queries';
import { useDemo } from '../../hooks/demo';
import { useScenarioMode } from '../../hooks/scenario';
import { Dialog } from '../../components/Dialog';
import { Badge, ErrorState } from '../../components/Primitives';
import { Link } from 'react-router-dom';

export function ReviewDialog({
  assessment,
  onClose,
}: {
  assessment: Assessment;
  onClose: () => void;
}) {
  const [rationale, setRationale] = useState('');
  const { role } = useDemo();
  const { final } = useScenarioMode();
  const review = useReview();
  const authorized = role === assessment.required_role;
  const decided = Boolean(assessment.reviewed_by);
  const unresolved =
    assessment.classification === 'UNRESOLVED' || assessment.status === 'MANUAL_REVIEW_REQUIRED';
  const valid = rationale.trim().length >= 10;
  function submit(decision: 'APPROVE' | 'REJECT') {
    review.mutate(
      { id: assessment.id, decision, rationale: rationale.trim(), role, reviewer: 'Demo reviewer' },
      { onSuccess: onClose },
    );
  }
  return (
    <Dialog
      title={decided ? 'Recorded scenario decision' : 'Review prospective mapping'}
      onClose={onClose}
    >
      <Badge tone="amber">{final ? 'Final rules' : 'Proposal'} · baseline remains unchanged</Badge>
      <h3>{assessment.mandate_title}</h3>
      <div className="mapping-target">
        <span className="eyebrow">PROPOSED SCENARIO TREATMENT</span>
        <strong>
          {assessment.target_id} · {assessment.target_label}
        </strong>
        <p>{assessment.recommendation}</p>
      </div>
      <p className="body-copy">{assessment.reason}</p>
      <div className="callout">
        <div>
          <strong>Human judgment required</strong>
          <p>
            This records a scenario decision only. It does not amend the current policy, control or
            regulatory baseline.
          </p>
        </div>
      </div>
      {decided ? (
        <section>
          <h3>{humanize(assessment.status)}</h3>
          <p className="body-copy">{assessment.rationale}</p>
          <p className="fine-print">
            Recorded by {assessment.reviewed_by}. Reset the demo to begin a new review.
          </p>
        </section>
      ) : (
        <>
          <label className="form-label" htmlFor="review-rationale">
            Your decision rationale
          </label>
          <textarea
            id="review-rationale"
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            placeholder="Explain why this prospective mapping is suitable or should be rejected…"
            rows={5}
            maxLength={2000}
            disabled={unresolved}
            aria-describedby="rationale-help"
          />
          <p id="rationale-help" className="fine-print">
            At least 10 characters. Saved with the demo reviewer and decision.
          </p>
          {unresolved ? (
            <p className="role-warning">
              Confirm change effect first.{' '}
              <Link to={`/mandates/${assessment.mandate_id}`} onClick={onClose}>
                Open mandate review
              </Link>{' '}
              to inspect evidence and confirm the classification.
            </p>
          ) : (
            !authorized && (
              <p className="role-warning">
                Switch the demo reviewer role to {assessment.required_role} to record this decision.
              </p>
            )
          )}
          {review.error && <ErrorState error={review.error} />}
          <div className="dialog-actions">
            <button
              className="button button-danger"
              disabled={!authorized || !valid || unresolved || review.isPending}
              onClick={() => submit('REJECT')}
            >
              <X size={16} />
              Reject
            </button>
            <button
              className="button button-primary"
              disabled={!authorized || !valid || unresolved || review.isPending}
              onClick={() => submit('APPROVE')}
            >
              <Check size={16} />
              {review.isPending ? 'Saving…' : 'Approve scenario mapping'}
            </button>
          </div>
        </>
      )}
    </Dialog>
  );
}
