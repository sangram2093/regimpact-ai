import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Play, Workflow } from 'lucide-react';
import { dashboardQuery } from '../api/queries';
import { runsQuery, useWorkflowRun } from '../api/workflows';
import type { WorkflowKind } from '../types/workflows';
import { Badge, ErrorState, LoadingState, PageHeading } from '../components/Primitives';
import { WorkflowRunCard } from '../components/WorkflowRunCard';

const kinds: WorkflowKind[] = [
  'change-effect',
  'pcs-extract',
  'interpret',
  'policy-map',
  'risk-map',
  'impact-explain',
];

const kindLabels: Record<WorkflowKind, string> = {
  'change-effect': 'Classify the change effect (Gemini)',
  'pcs-extract': 'Extract proposed changes from the consultation PDF (Gemini)',
  interpret: 'Interpret baseline obligations from the guideline PDF (Gemini)',
  'policy-map': 'Recommend a policy mapping from hybrid search (Gemini)',
  'risk-map': 'Suggest a risk classification (Gemini)',
  'impact-explain': 'Explain control impact from approved paths (Gemini)',
};

export function RunsPage() {
  const query = useQuery(runsQuery);
  const dashboard = useQuery(dashboardQuery);
  const mutation = useWorkflowRun();
  const [kind, setKind] = useState<WorkflowKind>('change-effect');
  const [changeId, setChangeId] = useState('');
  const change =
    dashboard.data?.changes.find((item) => item.id === changeId) ?? dashboard.data?.changes[0];
  return (
    <>
      <PageHeading
        eyebrow="BOUNDED WORKFLOWS / PROVENANCE"
        title="Every run, accounted for."
        description="Inspect actual model usage, validation and timing. A missing configuration is a visible status, never a simulated success."
      />
      <section className="panel workflow-launcher">
        <div className="panel-header">
          <h2>
            <Workflow size={20} />
            Run a bounded workflow
          </h2>
          <Badge>AI recommendations require review</Badge>
        </div>
        <div className="workflow-fields">
          <label>
            Workflow
            <select
              className="form-select"
              value={kind}
              onChange={(event) => setKind(event.target.value as WorkflowKind)}
            >
              {kinds.map((item) => (
                <option key={item} value={item}>
                  {kindLabels[item]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Scenario change
            <select
              className="form-select"
              value={change?.id ?? ''}
              onChange={(event) => setChangeId(event.target.value)}
            >
              {dashboard.data?.changes.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button button-primary"
            disabled={!change || mutation.isPending}
            onClick={() =>
              mutation.mutate({ kind, change_id: change!.id, mandate_id: change!.mandate_id })
            }
          >
            <Play size={14} />
            {mutation.isPending ? 'Running workflow…' : 'Run workflow'}
          </button>
        </div>
        <p className="fine-print">
          This does not approve a mandate or mapping. The backend selects the configured execution
          mode and fails closed when required services or source evidence are unavailable.
        </p>
        {dashboard.error && <ErrorState error={dashboard.error} />}
        {mutation.error && <ErrorState error={mutation.error} />}
        {mutation.isPending && (
          <p className="muted" role="status">
            Preparing bounded context and validating structured output…
          </p>
        )}
        {mutation.data && (
          <div className="page-section">
            <WorkflowRunCard run={mutation.data} />
          </div>
        )}
      </section>
      {query.isPending ? (
        <LoadingState label="Loading workflow provenance…" />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <section className="page-section">
          <div className="section-heading">
            <h2>Run history</h2>
            <Badge>{query.data.runs.length} recorded runs</Badge>
          </div>
          {query.data.runs.length ? (
            <div className="run-history">
              {query.data.runs.map((run) => (
                <WorkflowRunCard key={run.id} run={run} />
              ))}
            </div>
          ) : (
            <div className="panel empty-run-state">
              <Workflow size={30} />
              <h3>No workflow runs yet</h3>
              <p>
                Run a workflow or ask a graph question to create a provenance record. Seeded
                baseline data is not a live model run.
              </p>
            </div>
          )}
        </section>
      )}
    </>
  );
}
