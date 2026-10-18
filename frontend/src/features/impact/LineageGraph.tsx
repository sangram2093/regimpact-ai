import { humanize } from '../../utils/format';
import { ArrowRight, FileCheck2, GitBranch, ShieldCheck } from 'lucide-react';
import type { Impact } from '../../types/api';
import { useScenarioMode } from '../../hooks/scenario';

const groups = [
  { match: 'MANDATE', label: '01 / MANDATE', icon: GitBranch },
  { match: 'POLICY', label: '02 / POLICY REQUIREMENT', icon: FileCheck2 },
  { match: 'CONTROL', label: '03 / CONTROL OBJECTIVE', icon: ShieldCheck },
];

export function LineageGraph({
  impact,
  onExplain,
  unfilteredNodes = impact.nodes,
}: {
  impact: Impact;
  onExplain: (id: string) => void;
  unfilteredNodes?: Impact['nodes'];
}) {
  const { final } = useScenarioMode();
  return (
    <div className="lineage-graph" aria-label="Mandate to policy to control lineage">
      {groups.map(({ match, label, icon: Icon }, index) => (
        <div className="lineage-column" key={match}>
          <p className="graph-label">{label}</p>
          <div className="graph-nodes">
            {impact.nodes
              .filter((node) => node.type.toUpperCase().includes(match))
              .map((node) => (
                <div className={`graph-node graph-node-${index}`} key={node.id}>
                  <Icon size={22} />
                  <code>{node.id}</code>
                  <strong>{node.label}</strong>
                  {impact.controls.some((control) => control.id === node.id) && (
                    <span className="graph-impact-label">
                      {final ? 'Review needed' : 'Prospective impact'}
                    </span>
                  )}
                  <span
                    className={`graph-status ${['PROPOSED', 'SCENARIO_APPROVED'].includes(node.status) ? 'graph-status-proposed' : ''}`}
                  >
                    <span />
                    {humanize(node.status)}
                  </span>
                </div>
              ))}
            {!impact.nodes.some((node) => node.type.toUpperCase().includes(match)) && (
              <div className="graph-gap">
                {unfilteredNodes.some((node) => node.type.toUpperCase().includes(match))
                  ? `${humanize(match)} hidden by view filter`
                  : `No ${match.toLowerCase()} mapping`}
              </div>
            )}
          </div>
          {index < groups.length - 1 && <ArrowRight className="graph-connector" size={24} />}
        </div>
      ))}
      <div className="graph-edge-actions">
        <span>
          {impact.edges.length ? 'Inspect a relationship' : 'No relationships in this view'}
        </span>
        {impact.edges.map((edge) => (
          <button
            key={edge.id}
            onClick={() => onExplain(edge.id)}
            className={`edge-button ${edge.status === 'SCENARIO_APPROVED' ? 'edge-scenario' : ''}`}
            aria-label={`Explain edge ${edge.source} to ${edge.target}`}
          >
            <span>{edge.source}</span>
            <ArrowRight size={13} />
            <span>{edge.target}</span>
            {edge.status === 'SCENARIO_APPROVED' && <span>· Scenario approved</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
