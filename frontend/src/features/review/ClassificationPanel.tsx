import { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useClassification } from '../../api/workflows';
import type { ChangeDetail } from '../../types/api';
import type { ClassificationInput } from '../../types/workflows';
import { useDemo } from '../../hooks/demo';
import { ErrorState } from '../../components/Primitives';

export function ClassificationPanel({ change }: { change: ChangeDetail }) {
  const [classification, setClassification] = useState<ClassificationInput['classification']>(
    ['MODIFIED', 'UNCHANGED', 'NEW', 'REMOVED'].includes(change.classification)
      ? (change.classification as ClassificationInput['classification'])
      : 'MODIFIED',
  );
  const [rationale, setRationale] = useState('');
  const [evidenceSeen, setEvidenceSeen] = useState(false);
  const { role } = useDemo();
  const mutation = useClassification();
  const evidenceIds = [...change.baseline_evidence, ...change.proposal_evidence].map(
    (item) => item.id,
  );
  const authorized = role === 'Regulatory Specialist';
  const recorded = mutation.data?.classification_review ?? change.classification_review;
  if (recorded)
    return (
      <section className="panel page-section classification-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">HUMAN CONFIRMATION</p>
            <h2>Change effect confirmed</h2>
          </div>
          <ShieldCheck size={21} />
        </div>
        <p className="body-copy">{recorded.rationale}</p>
        <dl className="metadata-list">
          <div>
            <dt>Classification</dt>
            <dd>{recorded.classification}</dd>
          </div>
          <div>
            <dt>Reviewer</dt>
            <dd>{recorded.reviewer}</dd>
          </div>
          <div>
            <dt>Reviewed at</dt>
            <dd>{new Date(recorded.reviewed_at).toLocaleString()}</dd>
          </div>
        </dl>
        <p className="fine-print">
          Recorded for this scenario. Baseline knowledge remains unchanged. Reset the demo to start
          a new judgment.
        </p>
      </section>
    );
  return (
    <section className="panel page-section classification-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">HUMAN CONFIRMATION</p>
          <h2>Confirm the change effect</h2>
        </div>
        <ShieldCheck size={21} />
      </div>
      <p className="muted">
        Record specialist judgment against the source evidence. An unchanged classification never
        overrides scope, legal-force or semantic no-effect safeguards.
      </p>
      <div className="classification-fields">
        <div>
          <label className="form-label" htmlFor="classification">
            Classification
          </label>
          <select
            className="form-select"
            id="classification"
            value={classification}
            onChange={(event) =>
              setClassification(event.target.value as ClassificationInput['classification'])
            }
          >
            <option value="MODIFIED">Modified</option>
            <option value="UNCHANGED">Unchanged</option>
            <option value="NEW">New</option>
            <option value="REMOVED">Removed</option>
          </select>
        </div>
        <div>
          <label className="form-label" htmlFor="classification-rationale">
            Specialist rationale
          </label>
          <textarea
            id="classification-rationale"
            rows={3}
            maxLength={2000}
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            placeholder="Explain the change effect, including scope and proposed legal force…"
          />
        </div>
      </div>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={evidenceSeen}
          onChange={(event) => setEvidenceSeen(event.target.checked)}
        />
        I reviewed the baseline and proposal evidence displayed above.
      </label>
      {!authorized && (
        <p className="role-warning">
          Switch the demo reviewer role to Regulatory Specialist to confirm a classification.
        </p>
      )}
      <button
        className="button button-primary"
        disabled={
          !authorized ||
          !evidenceSeen ||
          evidenceIds.length === 0 ||
          rationale.trim().length < 10 ||
          mutation.isPending
        }
        onClick={() =>
          mutation.mutate({
            id: change.id,
            classification,
            rationale: rationale.trim(),
            evidence_ids: evidenceIds,
            reviewer: 'Demo reviewer',
            role,
          })
        }
      >
        <ShieldCheck size={16} />
        {mutation.isPending ? 'Recording judgment…' : 'Confirm change effect'}
      </button>
      {mutation.error && <ErrorState error={mutation.error} />}
      {mutation.isSuccess && (
        <p className="success-notice" role="status">
          Specialist judgment recorded for this scenario. Dependent review states have been
          refreshed.
        </p>
      )}
    </section>
  );
}
