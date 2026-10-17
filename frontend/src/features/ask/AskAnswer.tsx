import { CheckCheck, ExternalLink, ShieldAlert } from 'lucide-react';
import type { AskResponse } from '../../types/workflows';
import { Badge } from '../../components/Primitives';
import { WorkflowRunCard } from '../../components/WorkflowRunCard';
import { humanize } from '../../utils/format';

const fallback = "I couldn't ground a complete answer in approved graph data.";

export function AskAnswer({ result }: { result: AskResponse }) {
  const grounded =
    result.grounded &&
    result.total_references > 0 &&
    result.verified_references === result.total_references;
  const citations = new Set(result.citations.map((citation) => citation.id));
  const fragments = (grounded ? result.answer : fallback).split(/(\[[\w-]+\])/g);
  return (
    <section className="ask-result" aria-label="Grounded answer">
      <article className="panel answer-panel">
        <div className="panel-header">
          <h2>
            {grounded ? (
              <>
                <CheckCheck size={21} />
                Evidence-backed answer
              </>
            ) : (
              <>
                <ShieldAlert size={21} />
                Evidence is insufficient
              </>
            )}
          </h2>
          <Badge tone={grounded ? 'teal' : 'amber'}>
            {grounded
              ? `Grounded · ${result.verified_references} / ${result.total_references} references verified`
              : 'Answer withheld'}
          </Badge>
        </div>
        <div className="answer-text">
          {fragments.map((part, index) => {
            const id = part.slice(1, -1);
            return part.startsWith('[') && citations.has(id) ? (
              <a key={index} className="citation-link" href={`#cite-${id}`}>
                {part}
              </a>
            ) : (
              <span key={index}>{part}</span>
            );
          })}
        </div>
        <p className="fine-print">
          Read-only answer from this run’s tool results. Current baseline and prospective scenario
          decisions remain separate.
        </p>
      </article>
      {grounded && (
        <section className="panel page-section">
          <div className="panel-header">
            <h2>Supporting references</h2>
            <Badge>{result.citations.length} retrieved references</Badge>
          </div>
          <div className="citation-list">
            {result.citations.map((citation) => (
              <article className="citation-card" id={`cite-${citation.id}`} key={citation.id}>
                <div className="candidate-heading">
                  <code>[{citation.id}]</code>
                  <Badge>{humanize(citation.type)}</Badge>
                </div>
                <h3>{citation.label}</h3>
                {citation.excerpt && <p>{citation.excerpt}</p>}
                {citation.source_url && /^https:\/\//i.test(citation.source_url) && (
                  <a
                    className="text-link"
                    href={citation.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Inspect public source <ExternalLink size={12} />
                  </a>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
      <section className="panel page-section">
        <div className="panel-header">
          <h2>Tool activity</h2>
          <Badge>Read only</Badge>
        </div>
        {result.tool_calls.length ? (
          <ol className="tool-activity">
            {result.tool_calls.map((call, index) => (
              <li key={`${call.name}-${index}`}>
                <span className="tool-number">{index + 1}</span>
                <div>
                  <strong>{call.name}</strong>
                  <p>{call.summary}</p>
                </div>
                <Badge>{humanize(call.status)}</Badge>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No graph tool results were available for this question.</p>
        )}
      </section>
      <div className="page-section">
        <WorkflowRunCard run={result.run} />
      </div>
    </section>
  );
}
