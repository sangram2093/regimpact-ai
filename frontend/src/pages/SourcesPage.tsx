import { useQuery } from '@tanstack/react-query';
import { ExternalLink, FileCheck2, Fingerprint, RefreshCw } from 'lucide-react';
import { sourcesQuery, useIngestSource } from '../api/workflows';
import { Badge, ErrorState, LoadingState, PageHeading } from '../components/Primitives';
import { humanize } from '../utils/format';

export function SourcesPage() {
  const query = useQuery(sourcesQuery);
  const ingest = useIngestSource();
  return (
    <>
      <PageHeading
        eyebrow="PUBLIC SOURCES / VERIFIABLE EVIDENCE"
        title="Start with the source."
        description="Know which document an interpretation came from, what was ingested and what still needs verification."
      />
      {query.isPending ? (
        <LoadingState label="Inspecting the source register…" />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <div className="source-list">
            {query.data.sources.map((source) => (
              <article className="panel source-card" key={source.id}>
                <div className="panel-header">
                  <span className="source-icon">
                    <FileCheck2 size={24} />
                  </span>
                  <div>
                    <p className="eyebrow">
                      {source.regulator} · {source.publication_date}
                    </p>
                    <h2>{source.title}</h2>
                  </div>
                  <Badge tone={source.sha256 ? 'teal' : 'amber'}>
                    {humanize(source.ingestion_status)}
                  </Badge>
                </div>
                <div className="inline-badges">
                  <Badge>{humanize(source.legal_status)}</Badge>
                  <Badge>Public regulatory source</Badge>
                </div>
                <p className="body-copy source-note">{source.verification_note}</p>
                <div className="source-details">
                  <div>
                    <span>Document ID</span>
                    <strong>{source.id}</strong>
                  </div>
                  <div>
                    <span>Extracted segments</span>
                    <strong>{source.segment_count}</strong>
                  </div>
                  <div>
                    <span>Retrieved at</span>
                    <strong>
                      {source.retrieved_at
                        ? new Date(source.retrieved_at).toLocaleString()
                        : 'Not yet retrieved'}
                    </strong>
                  </div>
                </div>
                <div className="source-hash">
                  <Fingerprint size={17} />
                  <div>
                    <span>SHA-256 · Downloaded artifact</span>
                    <code>{source.sha256 ?? 'Unavailable — no verified downloaded artifact'}</code>
                  </div>
                </div>
                <div className="source-actions">
                  {/^https:\/\//i.test(source.source_url) && (
                    <a
                      className="text-link"
                      href={source.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open official source <ExternalLink size={14} />
                    </a>
                  )}
                  <button
                    className="button button-secondary"
                    onClick={() => ingest.mutate(source.id)}
                    disabled={!source.can_ingest || ingest.isPending}
                  >
                    <RefreshCw size={14} />
                    {ingest.isPending && ingest.variables === source.id
                      ? 'Extracting…'
                      : 'Ingest downloaded document'}
                  </button>
                </div>
                {!source.can_ingest && (
                  <p className="fine-print">
                    Ingestion becomes available after this known public document has been downloaded
                    and validated.
                  </p>
                )}
                {ingest.error && ingest.variables === source.id && (
                  <ErrorState error={ingest.error} />
                )}
                {ingest.isSuccess && ingest.variables === source.id && (
                  <p className="success-notice" role="status">
                    Source ingestion finished. The register now reflects the extracted artifact.
                  </p>
                )}
              </article>
            ))}
          </div>
          <div className="callout page-section">
            <FileCheck2 size={19} />
            <div>
              <strong>Evidence before interpretation</strong>
              {query.data.disclosures.map((text) => (
                <p key={text}>{text}</p>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}
