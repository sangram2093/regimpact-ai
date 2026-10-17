import { humanize } from '../utils/format';
import { ExternalLink, FileText } from 'lucide-react';
import type { Evidence } from '../types/api';
import { Badge } from './Primitives';

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const verified = evidence.text_kind === 'VERIFIED_EXCERPT';
  const safeUrl = /^https:\/\//i.test(evidence.source_url) ? evidence.source_url : undefined;
  return (
    <article className="evidence-card">
      <div className="evidence-top">
        <FileText size={16} />
        <span>
          {evidence.paragraph_ref}
          {evidence.page ? ` · Page ${evidence.page}` : ''}
        </span>
        <Badge tone={verified ? 'teal' : 'neutral'}>
          {verified ? 'Verified excerpt' : 'Paraphrase'}
        </Badge>
      </div>
      {verified ? (
        <blockquote>{evidence.text}</blockquote>
      ) : (
        <p className="evidence-text">{evidence.text}</p>
      )}
      <div className="evidence-footer">
        <span>{humanize(evidence.verification_status)}</span>
        {safeUrl && (
          <a href={safeUrl} target="_blank" rel="noreferrer">
            Public MAS source <ExternalLink size={12} />
          </a>
        )}
      </div>
    </article>
  );
}
