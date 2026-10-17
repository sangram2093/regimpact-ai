import { useQuery } from '@tanstack/react-query';
import { ArrowRight, FileCheck2 } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { mandatesQuery } from '../api/workflows';
import {
  Badge,
  ErrorState,
  LoadingState,
  PageHeading,
  ProposalBanner,
} from '../components/Primitives';
import { EvidenceCard } from '../components/EvidenceCard';
import { PolicyMappingPanel } from '../features/review/PolicyMappingPanel';
import { humanize } from '../utils/format';

export function MandatesPage() {
  const query = useQuery(mandatesQuery);
  const { id } = useParams();
  const selected = query.data?.mandates.find((mandate) => mandate.id === id);
  return (
    <>
      <PageHeading
        eyebrow="INTERPRETATION / HUMAN REVIEW"
        title="Mandates & mappings"
        description="Connect a source-backed obligation to a bounded set of enterprise policies, with specialist judgment at every decision."
      />
      <ProposalBanner />
      {query.isPending ? (
        <LoadingState label="Loading mandate interpretations…" />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : id && !selected ? (
        <div className="panel page-section">
          <h2>Mandate not found</h2>
          <Link className="text-link" to="/mandates">
            Return to mandate review
          </Link>
        </div>
      ) : selected ? (
        <>
          <nav className="change-tabs" aria-label="Select mandate">
            {query.data.mandates.map((mandate) => (
              <Link
                key={mandate.id}
                to={`/mandates/${mandate.id}`}
                className={mandate.id === id ? 'selected' : ''}
              >
                {mandate.title}
              </Link>
            ))}
          </nav>
          <div className="mandate-review-layout">
            <section className="panel mandate-evidence-panel">
              <div className="inline-badges">
                <Badge tone="amber">{humanize(selected.status)}</Badge>
                <Badge>{selected.classification}</Badge>
              </div>
              <p className="id-label page-section">{selected.id}</p>
              <h2>{selected.title}</h2>
              <p className="body-copy">{selected.text}</p>
              <p className="fine-print">Review state: {humanize(selected.review_status)}</p>
              <Badge tone={selected.classification_confirmed ? 'teal' : 'amber'}>
                {selected.classification_confirmed
                  ? 'Change effect confirmed by specialist'
                  : 'Specialist change confirmation required'}
              </Badge>
              <h3>Source evidence</h3>
              {selected.evidence.map((evidence) => (
                <EvidenceCard key={evidence.id} evidence={evidence} />
              ))}
              {selected.evidence.length === 0 && (
                <p className="muted">
                  Evidence is incomplete. Inspect the source register before authorizing
                  interpretation.
                </p>
              )}
              <Link className="text-link page-section" to={`/changes/${selected.change_id}`}>
                Compare and confirm change effect <ArrowRight size={15} />
              </Link>
            </section>
            <PolicyMappingPanel mandate={selected} />
          </div>
        </>
      ) : (
        <div className="mandate-grid page-section">
          {query.data.mandates.map((mandate) => (
            <article className="panel mandate-card" key={mandate.id}>
              <div className="panel-header">
                <FileCheck2 size={22} />
                <Badge tone={mandate.classification === 'NEW' ? 'amber' : 'teal'}>
                  {mandate.classification}
                </Badge>
              </div>
              <p className="id-label">{mandate.id}</p>
              <h2>{mandate.title}</h2>
              <p className="muted">{mandate.text}</p>
              <div className="inline-badges">
                <Badge>{humanize(mandate.review_status)}</Badge>
                <Badge>{mandate.evidence.length} evidence references</Badge>
              </div>
              <Link className="button button-secondary page-section" to={`/mandates/${mandate.id}`}>
                Review mandate and candidates <ArrowRight size={15} />
              </Link>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
