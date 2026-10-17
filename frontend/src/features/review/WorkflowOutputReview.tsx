import { useId, useState } from 'react';
import { CheckCheck, FilePenLine, ShieldCheck } from 'lucide-react';
import { useWorkflowOutputReview } from '../../api/workflows';
import { useDemo } from '../../hooks/demo';
import type {
  WorkflowOutputDecision,
  WorkflowOutputReviewInput,
  WorkflowResult,
} from '../../types/workflows';
import { Badge, ErrorState } from '../../components/Primitives';
import { humanize } from '../../utils/format';

function RecordedWorkflowDecision({ decision }: { decision: WorkflowOutputDecision }) {
  return (
    <section className="workflow-review-record">
      <div className="panel-header">
        <h3>
          <CheckCheck size={17} />
          Recorded specialist decision
        </h3>
        <Badge tone={decision.decision === 'REJECT' ? 'red' : 'teal'}>
          {humanize(decision.decision)}
        </Badge>
      </div>
      <p className="body-copy">{decision.rationale}</p>
      <dl className="metadata-list">
        <div>
          <dt>Reviewer / role</dt>
          <dd>
            {decision.reviewer} · {decision.role}
          </dd>
        </div>
        <div>
          <dt>Recorded at</dt>
          <dd>{new Date(decision.reviewed_at).toLocaleString()}</dd>
        </div>
      </dl>
      <details className="decision-audit">
        <summary>Compare original and reviewed output</summary>
        <div className="review-output-comparison">
          <div>
            <h4>Original recommendation</h4>
            <pre tabIndex={0} aria-label="Original workflow output">
              {JSON.stringify(decision.previous_output, null, 2)}
            </pre>
          </div>
          <div>
            <h4>Final reviewed output</h4>
            <pre tabIndex={0} aria-label="Final reviewed workflow output">
              {decision.final_output === null
                ? 'Rejected — no accepted final output.'
                : JSON.stringify(decision.final_output, null, 2)}
            </pre>
          </div>
        </div>
      </details>
      <p className="fine-print">
        The original recommendation is preserved. This recorded decision is read-only.
      </p>
    </section>
  );
}

export function WorkflowOutputReview({ result }: { result: WorkflowResult }) {
  const { role } = useDemo();
  const mutation = useWorkflowOutputReview();
  const [decision, setDecision] = useState<WorkflowOutputReviewInput['decision']>('APPROVE');
  const [rationale, setRationale] = useState('');
  const [modifiedJson, setModifiedJson] = useState(JSON.stringify(result.output, null, 2));
  const formId = useId();
  const recorded = mutation.data?.review ?? result.review;
  const liveAccepted =
    result.run.kind === 'LIVE_AI' &&
    result.run.validation_status === 'PASSED' &&
    result.output !== null &&
    result.run.status === 'SUCCEEDED';
  let finalOutput: Record<string, unknown> | undefined;
  let modificationError: string | null = null;
  if (decision === 'MODIFY') {
    try {
      const parsed: unknown = JSON.parse(modifiedJson);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed))
        throw new Error('object');
      finalOutput = parsed as Record<string, unknown>;
      if (JSON.stringify(finalOutput) === JSON.stringify(result.output))
        modificationError = 'Change the recommendation before submitting a modification.';
    } catch {
      modificationError =
        'Enter a valid JSON object. The server will also validate its schema, source evidence and allowed IDs.';
    }
  }
  const permitted = result.review_allowed === true && liveAccepted && role === result.required_role;
  const valid =
    permitted && rationale.trim().length >= 10 && !modificationError && !mutation.isPending;
  if (recorded) return <RecordedWorkflowDecision decision={recorded} />;
  if (!liveAccepted || result.review_allowed !== true)
    return (
      <div className="callout page-section">
        <ShieldCheck size={17} />
        <div>
          <strong>Human review is not available for this run</strong>
          <p>
            {result.block_reason ??
              'Only an accepted, validated live AI workflow output can enter this review step. Local deterministic results and unconfigured or failed runs cannot be approved as AI output.'}
          </p>
        </div>
      </div>
    );
  return (
    <section className="workflow-output-review">
      <div className="panel-header">
        <h3>
          <ShieldCheck size={18} />
          Review this AI recommendation
        </h3>
        <Badge tone="amber">{result.required_role ?? 'Specialist'} required</Badge>
      </div>
      <p className="muted">
        Approve, reject or modify the accepted structured output. Every decision preserves the
        original output, reviewed output and rationale. It does not automatically amend the approved
        regulatory baseline or enterprise catalog.
      </p>
      <label className="form-label" htmlFor={`${formId}-decision`}>
        Workflow review decision
      </label>
      <select
        id={`${formId}-decision`}
        className="form-select"
        value={decision}
        onChange={(event) =>
          setDecision(event.target.value as WorkflowOutputReviewInput['decision'])
        }
      >
        <option value="APPROVE">Approve recommendation</option>
        <option value="REJECT">Reject recommendation</option>
        <option value="MODIFY">Modify recommendation</option>
      </select>
      {decision === 'MODIFY' && (
        <>
          <label className="form-label" htmlFor={`${formId}-output`}>
            Reviewed structured output
          </label>
          <textarea
            className="json-editor"
            id={`${formId}-output`}
            rows={12}
            value={modifiedJson}
            onChange={(event) => setModifiedJson(event.target.value)}
            spellCheck={false}
            aria-describedby={`${formId}-json-help`}
          />
          <p id={`${formId}-json-help`} className="fine-print">
            Keep the workflow schema and existing source/candidate IDs. The backend revalidates
            edited objects before recording them.
          </p>
          {modificationError && (
            <p className="role-warning" role="status">
              {modificationError}
            </p>
          )}
        </>
      )}
      <label className="form-label" htmlFor={`${formId}-rationale`}>
        Workflow decision rationale
      </label>
      <textarea
        id={`${formId}-rationale`}
        rows={3}
        maxLength={2000}
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        placeholder="Explain the evidence and reasoning behind this decision…"
      />
      <p className="fine-print">At least 10 characters. Recorded with your demo reviewer role.</p>
      {role !== result.required_role && (
        <p className="role-warning">
          Switch the demo reviewer role to {result.required_role} to record this decision.
        </p>
      )}
      <button
        className={`button ${decision === 'REJECT' ? 'button-danger' : 'button-primary'}`}
        disabled={!valid}
        onClick={() =>
          mutation.mutate({
            id: result.run.id,
            decision,
            rationale: rationale.trim(),
            reviewer: 'Demo reviewer',
            role,
            ...(decision === 'MODIFY' ? { final_output: finalOutput } : {}),
          })
        }
      >
        {decision === 'MODIFY' ? <FilePenLine size={16} /> : <ShieldCheck size={16} />}
        {mutation.isPending
          ? 'Recording decision…'
          : decision === 'MODIFY'
            ? 'Save reviewed changes'
            : decision === 'REJECT'
              ? 'Reject workflow output'
              : 'Approve workflow output'}
      </button>
      {mutation.error && <ErrorState error={mutation.error} />}
    </section>
  );
}
