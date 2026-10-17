import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CheckCheck, GitBranch, Layers, ListChecks, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { dashboardQuery } from '../api/queries';
import { ErrorState, LoadingState, ProposalBanner } from '../components/Primitives';
import { ReviewMetric } from '../features/dashboard/ReviewMetric';
import { ChangeCard } from '../features/dashboard/ChangeCard';
import { DemoGuide } from '../components/DemoGuide';

export function DashboardPage() {
  const query = useQuery(dashboardQuery);
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const { metrics, scenario, changes } = query.data;
  const stats = [
    {
      label: 'Existing approved mappings',
      value: metrics.existing_mapping_items,
      detail: 'Baseline interpretation in scope',
      icon: Layers,
    },
    {
      label: 'Carry-forward candidates',
      value: metrics.carry_forward_candidates,
      detail: 'Must meet all safety checks',
      icon: CheckCheck,
    },
    {
      label: 'Individual re-reviews',
      value: metrics.individual_rechecks,
      detail: `${metrics.completed_rechecks} completed in this session`,
      icon: ListChecks,
    },
    {
      label: 'New proposed obligations',
      value: metrics.new_obligations,
      detail: 'Assessed separately from reuse',
      icon: Sparkles,
    },
  ];
  return (
    <>
      <div className="overview-intro">
        <p className="eyebrow">REGULATORY CHANGE-TO-CONTROL INTELLIGENCE</p>
        <span className="scenario-pill">
          <span />
          MAS · SINGAPORE
        </span>
      </div>
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-eyebrow">
            <GitBranch size={15} />
            THE DELTA REVIEW WORKSPACE
          </div>
          <h1>
            Review only
            <br />
            what <em>changed.</em>
          </h1>
          <p>
            Turn regulatory change into focused human review.
            <br className="desktop-break" /> Preserve what’s approved. Understand what needs
            attention.
          </p>
          <Link className="button button-primary" to="/delta-review">
            Open Delta Review <ArrowRight size={17} />
          </Link>
          <span className="hero-footnote">From rule change to control impact — with evidence.</span>
        </div>
        <ReviewMetric metrics={metrics} />
      </section>
      <ProposalBanner />
      <DemoGuide />
      <section className="stats-grid" aria-label="Scenario summary">
        {stats.map(({ label, value, detail, icon: Icon }) => (
          <article className="stat-card" key={label}>
            <div className="stat-label">
              <span>{label}</span>
              <Icon size={17} />
            </div>
            <strong>{value}</strong>
            <p>{detail}</p>
          </article>
        ))}
      </section>
      <section className="changes-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">ACTIVE HORIZON SCENARIO</p>
            <h2>What needs your attention</h2>
            <p>{scenario.title}</p>
          </div>
          <Link className="text-link" to="/changes">
            View change analysis <ArrowRight size={15} />
          </Link>
        </div>
        <div className="change-grid">
          {changes.map((change, index) => (
            <ChangeCard key={change.id} change={change} index={index} />
          ))}
        </div>
      </section>
      <div className="baseline-strip">
        <span className="baseline-icon">
          <CheckCheck size={20} />
        </span>
        <div>
          <strong>Approved baseline stays intact</strong>
          <p>
            {scenario.baseline_label} · Prospective decisions are isolated to your demo session.
          </p>
        </div>
        <Link to="/impact" className="text-link">
          Explore lineage <ArrowRight size={15} />
        </Link>
      </div>
    </>
  );
}
