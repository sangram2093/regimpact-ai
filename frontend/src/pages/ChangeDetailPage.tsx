import { humanize } from '../utils/format';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, GitBranch, Network, ShieldCheck } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { changeQuery } from '../api/queries';
import {
  Badge,
  ErrorState,
  LoadingState,
  PageHeading,
  ProposalBanner,
} from '../components/Primitives';
import { EvidenceCard } from '../components/EvidenceCard';
import { ClassificationPanel } from '../features/review/ClassificationPanel';
import { useScenarioMode } from '../hooks/scenario';

export function ChangeDetailPage() {
  const { id = '' } = useParams();
  const query = useQuery(changeQuery(id));
  const { copy, scenario } = useScenarioMode();
  if (query.isPending) return <LoadingState label="Loading source comparison…" />;
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const change = query.data;
  return (
    <>
      <Link className="back-link" to="/changes">
        <ArrowLeft size={15} />
        {copy.allChanges}
      </Link>
      <PageHeading
        eyebrow={`${change.id} / ${copy.sourceEyebrow}`}
        title={change.title}
        description={change.summary}
      />
      <ProposalBanner />
      <div className="inline-badges page-section">
        <Badge tone={change.classification === 'NEW' ? 'amber' : 'teal'}>
          {change.classification}
        </Badge>
        {change.change_nature.map((item) => (
          <Badge key={item}>{humanize(item)}</Badge>
        ))}
      </div>
      <section className="comparison-grid">
        <article className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">BEFORE</p>
              <h2>{copy.baselineTitle}</h2>
            </div>
            <Badge tone="teal">{copy.baselineBadge}</Badge>
          </div>
          <p className="panel-description">{scenario?.baseline_label}</p>
          {change.baseline_evidence.length ? (
            change.baseline_evidence.map((item) => <EvidenceCard key={item.id} evidence={item} />)
          ) : (
            <div className="empty-evidence">{copy.noBaseline}</div>
          )}
        </article>
        <article className="panel panel-proposal">
          <div className="panel-header">
            <div>
              <p className="eyebrow">{copy.changeEyebrow}</p>
              <h2>{copy.changeTitle}</h2>
            </div>
            <Badge tone="amber">{copy.changeBadge}</Badge>
          </div>
          <p className="panel-description">{scenario?.proposal_label}</p>
          {change.proposal_evidence.length ? (
            change.proposal_evidence.map((item) => <EvidenceCard key={item.id} evidence={item} />)
          ) : (
            <div className="empty-evidence">
              Not kept as a separate paragraph in the final text. Confirm whether other requirements
              cover it before retiring the mapping.
            </div>
          )}
        </article>
      </section>
      <ClassificationPanel key={change.id} change={change} />
      <div className="two-column page-section">
        <section className="panel">
          <div className="panel-header">
            <h2>Interpretation to review</h2>
            <GitBranch size={19} />
          </div>
          <p className="id-label">{change.mandate.id}</p>
          <h3>{change.mandate.title}</h3>
          <p className="muted">{copy.interpretationNote}</p>
          <div className="inline-badges">
            {change.risk_tags.map((tag) => (
              <Badge key={tag}>{tag}</Badge>
            ))}
          </div>
          <p className="fine-print">
            Risk classifications provide context; they do not expand control impact.
          </p>
          <Link className="text-link" to={`/mandates/${change.mandate.id}`}>
            Review policy candidates <ArrowRight size={15} />
          </Link>
        </section>
        <section className="next-step-card">
          <Network size={27} />
          <h2>Follow the impact.</h2>
          <p>See the approved mandate → policy → control paths that identify controls to review.</p>
          <Link className="button button-primary" to={`/impact/${change.id}`}>
            Explore impact lineage <ArrowRight size={16} />
          </Link>
          <Link className="text-link" to="/delta-review">
            <ShieldCheck size={15} />
            Review prospective mappings
          </Link>
        </section>
      </div>
    </>
  );
}
