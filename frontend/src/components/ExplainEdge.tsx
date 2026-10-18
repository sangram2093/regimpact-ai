import { humanize } from '../utils/format';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Database, ShieldCheck } from 'lucide-react';
import { edgeQuery } from '../api/queries';
import { Dialog } from './Dialog';
import { Badge, ErrorState, LoadingState } from './Primitives';
import { EvidenceCard } from './EvidenceCard';

export function ExplainEdge({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useQuery(edgeQuery(id));
  const edge = query.data;
  const scenario = edge?.status === 'SCENARIO_APPROVED';
  const provenance = edge?.provenance;
  const hasRun = Boolean(
    provenance &&
    (provenance.model ||
      provenance.prompt_version ||
      provenance.vector_rank != null ||
      provenance.lexical_rank != null ||
      provenance.rrf_rank != null),
  );
  return (
    <Dialog title="Explain this relationship" onClose={onClose}>
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        edge && (
          <>
            <div className="edge-identity">
              <code>{edge.source_id}</code>
              <ArrowRight size={18} />
              <code>{edge.target_id}</code>
            </div>
            <div className="inline-badges">
              <Badge tone={scenario ? 'amber' : 'teal'}>
                <ShieldCheck size={12} />
                {humanize(edge.status)}
              </Badge>
              <Badge>{humanize(edge.relationship)}</Badge>
            </div>
            <h3>Why this relationship exists</h3>
            <p className="body-copy">{edge.provenance.reason}</p>
            <div className="callout">
              <Database size={18} />
              <div>
                <strong>
                  {scenario ? 'Human-reviewed scenario provenance' : 'Curated seed provenance'}
                </strong>
                <p>
                  {edge.provenance.decision_source}.{' '}
                  {scenario
                    ? 'This prospective relationship is separate from the approved baseline. Only recorded retrieval and decision metadata are shown.'
                    : 'Curated by the team as a golden label. Run live hybrid retrieval and Gemini from Mandates & mappings to compare a fresh recommendation.'}
                </p>
              </div>
            </div>
            <h3>Decision provenance</h3>
            <dl className="metadata-list">
              <div>
                <dt>Proposed by</dt>
                <dd>{edge.provenance.proposed_by}</dd>
              </div>
              <div>
                <dt>Reviewer</dt>
                <dd>{edge.provenance.reviewer ?? 'Not recorded'}</dd>
              </div>
              <div>
                <dt>Reviewed at</dt>
                <dd>{edge.provenance.reviewed_at ?? 'Not recorded'}</dd>
              </div>
              {hasRun ? (
                <>
                  <div>
                    <dt>Model / prompt</dt>
                    <dd>
                      {edge.provenance.model ?? 'No model run'} /{' '}
                      {edge.provenance.prompt_version ?? 'Not applicable'}
                    </dd>
                  </div>
                  <div>
                    <dt>Vector / lexical rank</dt>
                    <dd>
                      {edge.provenance.vector_rank ?? '—'} / {edge.provenance.lexical_rank ?? '—'}
                    </dd>
                  </div>
                  <div>
                    <dt>RRF rank / score</dt>
                    <dd>
                      {edge.provenance.rrf_rank ?? '—'} / {edge.provenance.rrf_score ?? '—'}
                    </dd>
                  </div>
                </>
              ) : (
                <div>
                  <dt>Model / retrieval</dt>
                  <dd>Golden label — no model run or retrieval ranks recorded</dd>
                </div>
              )}
            </dl>
            <h3>Source evidence</h3>
            {edge.evidence.length ? (
              edge.evidence.map((item) => <EvidenceCard key={item.id} evidence={item} />)
            ) : (
              <p className="muted">
                Enterprise catalog relationship; synthetic data. No regulatory quotation is attached
                to this catalog edge.
              </p>
            )}
            <h3>Alternative considered</h3>
            <p className="body-copy">{edge.provenance.alternative ?? 'No alternative recorded.'}</p>
            {edge.provenance.alternative_reason && (
              <p className="muted">{edge.provenance.alternative_reason}</p>
            )}
            <p className="fine-print">
              Relationship {edge.id} · {edge.data_origin}
            </p>
          </>
        )
      )}
    </Dialog>
  );
}
