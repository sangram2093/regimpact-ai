import { useQuery } from '@tanstack/react-query';
import { dashboardQuery } from '../api/queries';
import { ErrorState, LoadingState, PageHeading, ProposalBanner } from '../components/Primitives';
import { ChangeCard } from '../features/dashboard/ChangeCard';
import { useScenarioMode } from '../hooks/scenario';

export function ChangesPage() {
  const query = useQuery(dashboardQuery);
  const { copy } = useScenarioMode();
  return (
    <>
      <PageHeading
        eyebrow={copy.changesEyebrow}
        title="Change analysis"
        description={copy.changesDescription}
      />
      <ProposalBanner />
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <div className="change-grid page-section">
          {query.data.changes.map((change, index) => (
            <ChangeCard key={change.id} change={change} index={index} />
          ))}
        </div>
      )}
    </>
  );
}
