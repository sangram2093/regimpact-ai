import { useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCheck, ClipboardCheck, ShieldCheck } from 'lucide-react';
import { impactAssessmentsQuery, useControlImpactReview } from '../../api/workflows';
import { useDemo } from '../../hooks/demo';
import type { ControlImpactAssessment, ControlImpactReviewInput } from '../../types/workflows';
import { Badge, ErrorState, LoadingState } from '../../components/Primitives';
import { Dialog } from '../../components/Dialog';
import { humanize } from '../../utils/format';
import { useScenarioMode } from '../../hooks/scenario';

function ImpactReviewDialog({
  assessment,
  onClose,
}: {
  assessment: ControlImpactAssessment;
  onClose: () => void;
}) {
  const { role } = useDemo();
  const { copy } = useScenarioMode();
  const mutation = useControlImpactReview();
  const [decision, setDecision] = useState<ControlImpactReviewInput['decision']>('APPROVE');
  const [rationale, setRationale] = useState('');
  const [scopeNote, setScopeNote] = useState(assessment.scope_note);
  const formId = useId();
  const saved = mutation.data ?? assessment;
  const validModification =
    decision !== 'MODIFY' ||
    (scopeNote.trim().length >= 10 && scopeNote.trim() !== assessment.scope_note.trim());
  const allowed =
    role === 'Policy Owner' &&
    rationale.trim().length >= 10 &&
    validModification &&
    !mutation.isPending;
  return (
    <Dialog
      title={saved.review ? 'Recorded control impact review' : 'Review prospective control impact'}
      onClose={onClose}
    >
      <Badge tone="amber">Prospective assessment · Catalog unchanged</Badge>
      <p className="id-label page-section">{assessment.control_id}</p>
      <h3>{assessment.title}</h3>
      <div className="mapping-target">
        <span className="eyebrow">{copy.scopeEyebrow}</span>
        <p>{saved.scope_note}</p>
      </div>
      <div className="callout page-section">
        <ShieldCheck size={18} />
        <div>
          <strong>Gate 6 · Human control impact review</strong>
          <p>
            The demo Policy Owner reviews the prospective impact and its scope. This records a
            scenario assessment only; it does not edit the control objective or assert that a
            control has been implemented.
          </p>
        </div>
      </div>
      {saved.review ? (
        <section>
          <h3>{humanize(saved.status)}</h3>
          <p className="body-copy">{saved.review.rationale}</p>
          <dl className="metadata-list">
            <div>
              <dt>Reviewed by</dt>
              <dd>
                {saved.review.reviewer} · {saved.review.role}
              </dd>
            </div>
            <div>
              <dt>Recorded at</dt>
              <dd>{new Date(saved.review.reviewed_at).toLocaleString()}</dd>
            </div>
          </dl>
          <details className="decision-audit">
            <summary>Inspect original and reviewed impact</summary>
            <h4>Original assessment</h4>
            <pre className="assessment-audit" tabIndex={0}>
              {JSON.stringify(saved.review.previous_output, null, 2)}
            </pre>
            <h4>Reviewed assessment</h4>
            <pre className="assessment-audit" tabIndex={0}>
              {saved.review.final_output === null
                ? 'Rejected — no accepted impact assessment.'
                : JSON.stringify(saved.review.final_output, null, 2)}
            </pre>
          </details>
          <p className="fine-print">
            This recorded assessment is read-only. Reset the demo to start a new decision.
          </p>
        </section>
      ) : (
        <>
          <label className="form-label" htmlFor={`${formId}-decision`}>
            Control impact decision
          </label>
          <select
            className="form-select"
            id={`${formId}-decision`}
            value={decision}
            onChange={(event) =>
              setDecision(event.target.value as ControlImpactReviewInput['decision'])
            }
          >
            <option value="APPROVE">Confirm prospective impact</option>
            <option value="REJECT">Reject prospective impact</option>
            <option value="MODIFY">Modify proposed scope</option>
          </select>
          {decision === 'MODIFY' && (
            <>
              <label className="form-label" htmlFor={`${formId}-scope`}>
                Reviewed impact scope
              </label>
              <textarea
                id={`${formId}-scope`}
                rows={4}
                maxLength={3000}
                value={scopeNote}
                onChange={(event) => setScopeNote(event.target.value)}
              />
              <p className="fine-print">
                Explain the revised prospective scope. The underlying control catalog is unchanged.
              </p>
            </>
          )}
          <label className="form-label" htmlFor={`${formId}-rationale`}>
            Control impact rationale
          </label>
          <textarea
            id={`${formId}-rationale`}
            rows={4}
            maxLength={2000}
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            placeholder="Explain why this control impact is suitable, unsuitable, or needs a different scope…"
          />
          <p className="fine-print">At least 10 characters. Recorded in your scenario session.</p>
          {role !== 'Policy Owner' && (
            <p className="role-warning">
              Switch the demo reviewer role to Policy Owner to record control impact.
            </p>
          )}
          <button
            className={`button ${decision === 'REJECT' ? 'button-danger' : 'button-primary'}`}
            disabled={!allowed}
            onClick={() =>
              mutation.mutate({
                id: assessment.id,
                decision,
                rationale: rationale.trim(),
                reviewer: 'Demo reviewer',
                role,
                ...(decision === 'MODIFY' ? { scope_note: scopeNote.trim() } : {}),
              })
            }
          >
            <ClipboardCheck size={16} />
            {mutation.isPending
              ? 'Recording review…'
              : decision === 'MODIFY'
                ? 'Save reviewed impact scope'
                : decision === 'REJECT'
                  ? 'Reject control impact'
                  : 'Confirm control impact'}
          </button>
          {mutation.error && <ErrorState error={mutation.error} />}
        </>
      )}
    </Dialog>
  );
}

export function ControlImpactReview({ changeId }: { changeId: string }) {
  const query = useQuery(impactAssessmentsQuery(changeId));
  const { copy, final } = useScenarioMode();
  const [selected, setSelected] = useState<ControlImpactAssessment | null>(null);
  return (
    <section className="panel page-section control-review-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">
            {final ? 'GATE 6 / CONTROL ASSESSMENT' : 'GATE 6 / PROSPECTIVE ASSESSMENT'}
          </p>
          <h2>Authorize control impact</h2>
        </div>
        <Badge>Demo Policy Owner</Badge>
      </div>
      <p className="muted">{copy.controlReviewIntro} Decisions preserve the enterprise catalog.</p>
      {query.isPending ? (
        <LoadingState label="Loading prospective impact assessments…" />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data.assessments.length === 0 ? (
        <p className="empty-evidence">
          No control impact assessments are available for this path. Complete policy and control
          coverage before authorizing an impact.
        </p>
      ) : (
        <div className="impact-assessment-list">
          {query.data.assessments.map((assessment) => (
            <article className="impact-assessment-row" key={assessment.id}>
              <span className="control-icon">
                <CheckCheck size={19} />
              </span>
              <div>
                <code>{assessment.control_id}</code>
                <h3>{assessment.title}</h3>
                <p>{assessment.scope_note}</p>
              </div>
              <div className="impact-assessment-actions">
                <Badge
                  tone={
                    assessment.status === 'REJECTED' ? 'red' : assessment.review ? 'teal' : 'amber'
                  }
                >
                  {humanize(assessment.status)}
                </Badge>
                <button
                  className="button button-small button-secondary"
                  onClick={() => setSelected(assessment)}
                >
                  {assessment.review ? 'View impact decision' : 'Review control impact'}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {selected && (
        <ImpactReviewDialog
          key={selected.id}
          assessment={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}
