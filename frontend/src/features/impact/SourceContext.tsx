import { useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { changeQuery } from '../../api/queries';
import { EvidenceCard } from '../../components/EvidenceCard';
import { Badge, ErrorState, LoadingState } from '../../components/Primitives';

function SourceReferences({ changeId }: { changeId: string }) {
  const query = useQuery(changeQuery(changeId));
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  if (query.isPending) return <LoadingState label="Loading source and provision references…" />;
  const detail = query.data;
  return (
    <>
      <p className="source-context-caption">
        Documentary context for <code>{detail.mandate.id}</code> · {detail.mandate.title}. These
        source locators are evidence references, not additional approved graph relationships.
      </p>
      <div className="source-context-columns">
        {[
          {
            title: 'Baseline source / provision',
            evidence: detail.baseline_evidence,
            proposal: false,
          },
          {
            title: 'Proposal source / provision',
            evidence: detail.proposal_evidence,
            proposal: true,
          },
        ].map((group) => (
          <section key={group.title} aria-label={group.title}>
            <div className="source-context-heading">
              <h3>{group.title}</h3>
              {group.proposal && <Badge tone="amber">Proposed</Badge>}
            </div>
            {group.evidence.length === 0 ? (
              <p className="source-context-empty">
                No {group.proposal ? 'proposal' : 'baseline'} evidence reference is supplied for
                this change.
              </p>
            ) : (
              group.evidence.map((evidence) => (
                <div className="source-context-reference" key={evidence.id}>
                  <p className="source-context-title">{evidence.title}</p>
                  <p className="source-context-id">
                    Source <code>{evidence.source_id}</code> · Evidence <code>{evidence.id}</code>
                  </p>
                  <EvidenceCard evidence={evidence} />
                </div>
              ))
            )}
          </section>
        ))}
      </div>
      <div className="source-context-footer">
        <span>Only references supplied for this change are shown.</span>
        <Link to="/sources">Open source register and ingestion status</Link>
      </div>
    </>
  );
}

export function SourceContext({ changeId }: { changeId: string }) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();
  return (
    <div className="source-context-expansion">
      <button
        className="source-context-toggle"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded((current) => !current)}
      >
        <FileText size={18} aria-hidden="true" />
        <span>
          <strong>{expanded ? 'Collapse' : 'Expand'} source and provision context</strong>
          <span>One level upstream · baseline and proposal evidence</span>
        </span>
        <ChevronDown size={18} className={expanded ? 'expanded' : ''} aria-hidden="true" />
      </button>
      <div id={contentId} hidden={!expanded} className="source-context-content">
        {expanded && <SourceReferences changeId={changeId} />}
      </div>
    </div>
  );
}
