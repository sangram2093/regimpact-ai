import { CheckCircle2, CircleAlert, Clock3, Cpu, Database } from 'lucide-react';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { runDetailQuery } from '../api/workflows';
import type { WorkflowRun } from '../types/workflows';
import { humanize } from '../utils/format';
import { Badge, ErrorState, LoadingState } from './Primitives';
import { WorkflowOutputReview } from '../features/review/WorkflowOutputReview';

function RunOutput({ run }: { run: WorkflowRun }) {
  const query = useQuery(runDetailQuery(run.id));
  if (query.isPending) return <LoadingState label="Loading recorded structured output…" />;
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return (
    <div className="run-output">
      <div className="inline-badges">
        <Badge tone="amber">
          {run.kind === 'LIVE_AI'
            ? 'AI suggestion · Human approval required'
            : 'Read-only workflow result'}
        </Badge>
        <Badge>{humanize(query.data.status)}</Badge>
      </div>
      {query.data.validation_errors.length > 0 && (
        <div className="role-warning">
          <strong>Validation did not pass</strong>
          <ul>
            {query.data.validation_errors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}
      {query.data.output === null ? (
        <p className="muted">No accepted structured output is available for this run.</p>
      ) : (
        <pre tabIndex={0} aria-label="Structured workflow output">
          {JSON.stringify(query.data.output, null, 2)}
        </pre>
      )}
      <p className="fine-print">
        Generated objects are recommendations only. They do not automatically change the
        authoritative graph.
      </p>
      <WorkflowOutputReview
        key={`${run.id}-${query.data.review?.reviewed_at ?? 'pending'}`}
        result={query.data}
      />
    </div>
  );
}

export function WorkflowRunCard({ run, compact = false }: { run: WorkflowRun; compact?: boolean }) {
  const live = run.kind === 'LIVE_AI';
  const [expanded, setExpanded] = useState(false);
  const success = run.status === 'SUCCEEDED';
  return (
    <article className={`run-card ${compact ? 'run-card-compact' : ''}`}>
      <div className="run-heading">
        <span className="run-icon">{live ? <Cpu size={18} /> : <Database size={18} />}</span>
        <div>
          <strong>{humanize(run.workflow)}</strong>
          <p>{run.label}</p>
        </div>
        <Badge tone={success ? 'teal' : 'amber'}>{humanize(run.status)}</Badge>
      </div>
      <div className="inline-badges">
        <Badge tone={live ? 'teal' : 'neutral'}>
          {live ? 'Live AI' : run.kind === 'SEED' ? 'Seed fixture' : 'Local deterministic'}
        </Badge>
        <Badge>{humanize(run.validation_status)} validation</Badge>
      </div>
      <dl className="run-metadata">
        <div>
          <dt>
            <Cpu size={12} />
            Model
          </dt>
          <dd>{run.model ?? 'No model call'}</dd>
        </div>
        <div>
          <dt>
            <Clock3 size={12} />
            Run time
          </dt>
          <dd>{run.started_at ? new Date(run.started_at).toLocaleString() : 'Not recorded'}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>
            {run.duration_ms === null ? 'Not recorded' : `${run.duration_ms.toLocaleString()} ms`}
          </dd>
        </div>
        <div>
          <dt>Prompt</dt>
          <dd>{run.prompt_version ?? 'Not applicable'}</dd>
        </div>
      </dl>
      {!compact && run.steps.length > 0 && (
        <ol className="run-steps">
          {run.steps.map((step, index) => (
            <li key={`${step.name}-${index}`}>
              {['SUCCEEDED', 'PASSED', 'COMPLETE'].includes(step.status) ? (
                <CheckCircle2 size={14} />
              ) : (
                <CircleAlert size={14} />
              )}
              <div>
                <strong>
                  {humanize(step.name)} <span>{humanize(step.status)}</span>
                </strong>
                <p>{step.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
      <p className="fine-print">Run {run.id}</p>
      {!compact && (
        <>
          <button
            className="button button-small button-secondary page-section"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Hide structured output' : 'Inspect structured output'}
          </button>
          {expanded && <RunOutput run={run} />}
        </>
      )}
    </article>
  );
}
