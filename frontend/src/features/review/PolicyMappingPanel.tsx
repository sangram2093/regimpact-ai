import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, GitBranch, X } from 'lucide-react';
import { candidatesQuery, usePolicyMapping } from '../../api/workflows';
import { useDemo } from '../../hooks/demo';
import type { MandateRecord, PolicyCandidates } from '../../types/workflows';
import { Badge, ErrorState, LoadingState } from '../../components/Primitives';
import { WorkflowRunCard } from '../../components/WorkflowRunCard';
import { humanize } from '../../utils/format';

function MappingReviewForm({ mandate, data }: { mandate: MandateRecord; data: PolicyCandidates }) {
  const [selected, setSelected] = useState(data.selected_policy_id ?? '');
  const [rationale, setRationale] = useState('');
  const { role } = useDemo();
  const mutation = usePolicyMapping();
  const unresolved = mandate.classification === 'UNRESOLVED';
  const decided = ['SCENARIO_APPROVED', 'SCENARIO_REJECTED', 'APPROVED', 'REJECTED'].includes(
    data.review_status,
  );
  const canSubmit =
    role === 'Policy Owner' &&
    !unresolved &&
    data.mapping_allowed === true &&
    !decided &&
    selected !== '' &&
    rationale.trim().length >= 10 &&
    !mutation.isPending;
  function submit(decision: 'APPROVE' | 'REJECT') {
    mutation.mutate({
      id: mandate.id,
      policy_id: selected,
      decision,
      rationale: rationale.trim(),
      role,
      reviewer: 'Demo reviewer',
    });
  }
  return (
    <>
      <div className="panel-header">
        <div>
          <p className="eyebrow">BOUNDED ENTERPRISE CANDIDATES</p>
          <h2>Find the policy connection</h2>
        </div>
        <Badge tone="amber">Prospective mapping</Badge>
      </div>
      <p className="muted">
        Review retrieved synthetic policy requirements. Approval creates a scenario relationship; it
        does not amend the approved baseline.
      </p>
      <WorkflowRunCard run={data.run} compact />
      {data.candidates.length === 0 ? (
        <div className="empty-evidence page-section">
          No suitable policy candidate was found. This coverage gap stays visible; the system will
          not invent a policy ID.
        </div>
      ) : (
        <fieldset className="candidate-list" disabled={decided}>
          <legend>Select a candidate to review</legend>
          {data.candidates.map((candidate) => (
            <label
              className={`candidate-card ${selected === candidate.id ? 'candidate-selected' : ''}`}
              key={candidate.id}
            >
              <input
                type="radio"
                name={`policy-${mandate.id}`}
                value={candidate.id}
                checked={selected === candidate.id}
                onChange={() => setSelected(candidate.id)}
              />
              <div>
                <div className="candidate-heading">
                  <code>{candidate.id}</code>
                  {candidate.rrf_rank !== null && <Badge>RRF rank {candidate.rrf_rank}</Badge>}
                </div>
                <h3>{candidate.title}</h3>
                <p>{candidate.text}</p>
                <p className="candidate-reason">{candidate.reason}</p>
                <dl className="candidate-ranks">
                  <div>
                    <dt>Vector rank</dt>
                    <dd>{candidate.vector_rank ?? 'Not run'}</dd>
                  </div>
                  <div>
                    <dt>Lexical rank</dt>
                    <dd>{candidate.lexical_rank ?? 'Not ranked'}</dd>
                  </div>
                  <div>
                    <dt>RRF score</dt>
                    <dd>
                      {candidate.rrf_score === null
                        ? 'Not computed'
                        : candidate.rrf_score.toFixed(5)}
                    </dd>
                  </div>
                </dl>
              </div>
            </label>
          ))}
        </fieldset>
      )}
      {decided ? (
        <div className="callout page-section">
          <Check size={18} />
          <div>
            <strong>{humanize(data.review_status)}</strong>
            <p>{data.rationale ?? 'The scenario mapping decision has been recorded.'}</p>
            <p>
              {data.reviewed_by ? `Reviewed by ${data.reviewed_by}. ` : ''}Reset the demo to start a
              new decision.
            </p>
          </div>
        </div>
      ) : (
        data.candidates.length > 0 && (
          <>
            <label className="form-label" htmlFor="mapping-rationale">
              Mapping decision rationale
            </label>
            <textarea
              id="mapping-rationale"
              rows={4}
              maxLength={2000}
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Explain how the selected policy addresses this mandate, or why it should be rejected…"
            />
            <p className="fine-print">
              At least 10 characters. Selection is limited to the returned candidate set.
            </p>
            {data.mapping_allowed !== true ? (
              <p className="role-warning">
                {data.mapping_block_reason ??
                  'Confirm the change effect against source evidence before recording a prospective mapping.'}
              </p>
            ) : unresolved ? (
              <p className="role-warning">
                Confirm the unresolved change effect before recording a mapping decision.
              </p>
            ) : (
              role !== 'Policy Owner' && (
                <p className="role-warning">
                  Switch the demo reviewer role to Policy Owner to record this prospective mapping.
                </p>
              )
            )}
            <div className="dialog-actions">
              <button
                className="button button-danger"
                disabled={!canSubmit}
                onClick={() => submit('REJECT')}
              >
                <X size={15} />
                Reject candidate
              </button>
              <button
                className="button button-primary"
                disabled={!canSubmit}
                onClick={() => submit('APPROVE')}
              >
                <GitBranch size={15} />
                {mutation.isPending ? 'Recording decision…' : 'Approve prospective mapping'}
              </button>
            </div>
          </>
        )
      )}
      {mutation.error && <ErrorState error={mutation.error} />}
      {mutation.isSuccess && (
        <p className="success-notice" role="status">
          Scenario mapping decision recorded. The baseline is unchanged.
        </p>
      )}
    </>
  );
}

export function PolicyMappingPanel({ mandate }: { mandate: MandateRecord }) {
  const query = useQuery(candidatesQuery(mandate.id));
  return (
    <section className="panel">
      {query.isPending ? (
        <LoadingState label="Retrieving bounded policy candidates…" />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <MappingReviewForm
          key={`${mandate.id}-${query.data.review_status}`}
          mandate={mandate}
          data={query.data}
        />
      )}
    </section>
  );
}
