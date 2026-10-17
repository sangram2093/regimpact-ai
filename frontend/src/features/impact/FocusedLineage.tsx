import { useId, useState } from 'react';
import type { Impact } from '../../types/api';
import { LineageGraph } from './LineageGraph';

// This only filters the returned view. Authoritative impact and coverage stay server-owned.
function controlPaths(impact: Impact, controlId: string): Impact {
  const visible = new Set(
    impact.controls
      .filter((control) => !controlId || control.id === controlId)
      .map((control) => control.id),
  );
  let expanded = true;
  while (expanded) {
    expanded = false;
    for (const edge of impact.edges) {
      if (visible.has(edge.target) && !visible.has(edge.source)) {
        visible.add(edge.source);
        expanded = true;
      }
    }
  }
  const edges = impact.edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target));
  // The selected mandate remains as context, including when the control coverage is empty.
  for (const node of impact.nodes) {
    if (node.type.toUpperCase().includes('MANDATE')) visible.add(node.id);
  }
  return { ...impact, nodes: impact.nodes.filter((node) => visible.has(node.id)), edges };
}

export function FocusedLineage({
  impact,
  onExplain,
}: {
  impact: Impact;
  onExplain: (id: string) => void;
}) {
  const [impactedOnly, setImpactedOnly] = useState(false);
  const [controlId, setControlId] = useState('');
  const selectId = useId();
  const shown = impactedOnly ? controlPaths(impact, controlId) : impact;
  return (
    <>
      <div className="lineage-view-filters" aria-label="Lineage view filters">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={impactedOnly}
            onChange={(event) => setImpactedOnly(event.target.checked)}
          />
          Impacted controls only
        </label>
        {impact.controls.length > 1 && (
          <div className="lineage-control-filter">
            <label htmlFor={selectId}>Focus an impacted control</label>
            <select
              id={selectId}
              className="form-select"
              value={controlId}
              onChange={(event) => {
                setControlId(event.target.value);
                setImpactedOnly(true);
              }}
            >
              <option value="">All impacted controls</option>
              {impact.controls.map((control) => (
                <option key={control.id} value={control.id}>
                  {control.id} · {control.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <p className="lineage-filter-summary" role="status">
        Showing {shown.edges.length} of {impact.edges.length} returned relationships. View filters
        do not change coverage or review totals.
      </p>
      {impactedOnly && shown.edges.length === 0 && (
        <p className="lineage-filter-empty">
          No connected control impact path is available in this view. The selected mandate and
          coverage status remain visible. Clear the filter to inspect all returned context.
        </p>
      )}
      <LineageGraph impact={shown} onExplain={onExplain} unfilteredNodes={impact.nodes} />
    </>
  );
}
