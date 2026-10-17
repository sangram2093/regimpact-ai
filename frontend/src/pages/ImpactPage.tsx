import { humanize } from '../utils/format';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CheckCheck, Info, Network } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { dashboardQuery, impactQuery } from '../api/queries';
import {
  Badge,
  ErrorState,
  LoadingState,
  PageHeading,
  ProposalBanner,
} from '../components/Primitives';
import { ExplainEdge } from '../components/ExplainEdge';
import { FocusedLineage } from '../features/impact/FocusedLineage';
import { SourceContext } from '../features/impact/SourceContext';
import { ControlImpactReview } from '../features/impact/ControlImpactReview';

export function ImpactPage() {
  const { id } = useParams();
  const dashboard = useQuery(dashboardQuery);
  const changeId = id ?? dashboard.data?.changes[0]?.id ?? '';
  const [includeScenario, setIncludeScenario] = useState(false);
  const query = useQuery(impactQuery(changeId, includeScenario));
  const [edgeId, setEdgeId] = useState<string | null>(null);
  const change = dashboard.data?.changes.find((item) => item.id === changeId);
  if (dashboard.error || query.error)
    return (
      <ErrorState
        error={dashboard.error ?? query.error!}
        retry={() => {
          void dashboard.refetch();
          void query.refetch();
        }}
      />
    );
  if (query.isPending || !dashboard.data)
    return <LoadingState label="Tracing approved compliance paths…" />;
  const impact = query.data;
  return (
    <>
      <PageHeading
        eyebrow="DETERMINISTIC GRAPH TRAVERSAL"
        title="Impact lineage"
        description="Every affected control has a traceable path. Risk taxonomy provides context without expanding impact."
      />
      <ProposalBanner />
      <nav className="change-tabs" aria-label="Select change for impact">
        {dashboard.data.changes.map((item) => (
          <Link
            key={item.id}
            className={changeId === item.id ? 'selected' : ''}
            to={`/impact/${item.id}`}
          >
            {item.title}
          </Link>
        ))}
      </nav>
      <div className="impact-view-controls">
        <div className="impact-source-context">
          <Link to="/sources">{dashboard.data.scenario.baseline_label}</Link>
          <span>Scenario: {dashboard.data.scenario.proposal_label}</span>
        </div>
        <div className="lineage-approval-filter">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={!includeScenario}
              onChange={(event) => setIncludeScenario(!event.target.checked)}
            />
            Approved baseline relationships only
          </label>
          <p>Uncheck to include reviewed scenario mappings.</p>
        </div>
      </div>
      {includeScenario && (
        <div className="scenario-view-notice">
          Human-approved scenario relationships are shown in amber. They remain prospective and do
          not replace baseline relationships.
        </div>
      )}
      <section className="panel lineage-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">PROSPECTIVE CONTROL IMPACT</p>
            <h2>{change?.title ?? changeId}</h2>
          </div>
          <Badge tone={impact.coverage === 'COMPLETE' ? 'teal' : 'amber'}>
            {impact.coverage === 'NO_POLICY_MAPPING'
              ? 'Coverage gap'
              : impact.coverage === 'PARTIAL'
                ? 'Partial control coverage'
                : `${impact.controls.length} distinct controls`}
          </Badge>
        </div>
        <SourceContext key={changeId} changeId={changeId} />
        <FocusedLineage
          key={`${changeId}-${includeScenario}`}
          impact={impact}
          onExplain={setEdgeId}
        />
        <div className="lineage-legend">
          <span>
            <i className="legend-dot" />
            Approved baseline relationship
          </span>
          <span>
            <i className="legend-line" />
            Enterprise catalog link
          </span>
          <span>Click a relationship to inspect its evidence</span>
          {includeScenario && (
            <span className="scenario-legend">Amber · Human-approved prospective mapping</span>
          )}
        </div>
      </section>
      {impact.coverage === 'NO_POLICY_MAPPING' ? (
        <div className="coverage-callout page-section">
          <Network size={30} />
          <div>
            <Badge tone="amber">NEW PROPOSED OBLIGATION</Badge>
            <h2>No approved policy mapping</h2>
            <p>
              This mandate has no approved path to an enterprise policy or control. Zero downstream
              controls means a coverage gap, not zero regulatory impact. Specialist mapping is
              required.
            </p>
            <Link className="text-link" to={`/changes/${changeId}`}>
              Inspect proposed obligation <ArrowRight size={15} />
            </Link>
            {change && (
              <Link
                className="button button-secondary page-section"
                to={`/mandates/${change.mandate_id}`}
              >
                Review policy candidates <ArrowRight size={15} />
              </Link>
            )}
          </div>
        </div>
      ) : (
        <section className="panel page-section">
          <div className="panel-header">
            <h2>Controls to review if adopted</h2>
            <Badge>Prospective impact</Badge>
          </div>
          <div className="control-list">
            {impact.coverage === 'PARTIAL' && (
              <p className="role-warning">
                A policy path exists, but approved control coverage is incomplete. A prospective
                policy mapping alone does not establish control coverage.
              </p>
            )}
            {impact.controls.length === 0 && (
              <p className="muted">No approved downstream controls are connected to this path.</p>
            )}
            {impact.controls.map((control) => (
              <div className="control-row" key={control.id}>
                <span className="control-icon">
                  <CheckCheck size={19} />
                </span>
                <div>
                  <code>{control.id}</code>
                  <strong>{control.title}</strong>
                </div>
                <Badge tone="amber">{humanize(control.impact_type)}</Badge>
              </div>
            ))}
          </div>
        </section>
      )}
      <ControlImpactReview key={changeId} changeId={changeId} />
      <div className="callout page-section">
        <Info size={18} />
        <div>
          <strong>Impact follows compliance lineage</strong>
          <p>Mandate → Policy Requirement → Control Objective. Risk tags are contextual only.</p>
          <div className="inline-badges">
            {impact.risk_tags.map((tag) => (
              <Badge key={tag}>{tag}</Badge>
            ))}
          </div>
        </div>
      </div>
      {edgeId && <ExplainEdge id={edgeId} onClose={() => setEdgeId(null)} />}
    </>
  );
}
