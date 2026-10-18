import { useQuery } from '@tanstack/react-query';
import { ArrowRight, CircleDot } from 'lucide-react';
import { Link } from 'react-router-dom';
import { dashboardQuery } from '../api/queries';
import {
  Badge,
  ErrorState,
  LoadingState,
  PageHeading,
  ProposalBanner,
} from '../components/Primitives';
import { useScenarioMode } from '../hooks/scenario';

export function CoveragePage() {
  const query = useQuery(dashboardQuery);
  const { copy } = useScenarioMode();
  return (
    <>
      <PageHeading
        eyebrow="PROSPECTIVE COVERAGE"
        title="Make the gaps visible."
        description={`${copy.newObligations} need explicit mapping. They are never silently absorbed into the approved graph.`}
      />
      <ProposalBanner />
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <div className="page-section">
          {query.data.changes
            .filter((change) => change.classification === 'NEW')
            .map((change) => (
              <section className="coverage-callout" key={change.id}>
                <CircleDot size={33} />
                <div>
                  <Badge tone="amber">{copy.newObligation}</Badge>
                  <h2>{change.title}</h2>
                  <p>{change.summary}</p>
                  <p className="muted">
                    A specialist must assess prospective policy coverage. Review bounded candidates
                    and record a separate scenario mapping.
                  </p>
                  <Link className="button button-primary" to={`/impact/${change.id}`}>
                    Inspect coverage and lineage <ArrowRight size={16} />
                  </Link>
                  <Link className="text-link page-section" to={`/mandates/${change.mandate_id}`}>
                    Review policy candidates <ArrowRight size={15} />
                  </Link>
                </div>
              </section>
            ))}
          {query.data.metrics.new_obligations === 0 && (
            <p className="panel">No {copy.newObligations.toLowerCase()} in this scenario.</p>
          )}
        </div>
      )}
    </>
  );
}
