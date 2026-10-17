import { useQuery } from '@tanstack/react-query';
import { dashboardQuery } from '../api/queries';
import { ErrorState, LoadingState, PageHeading, ProposalBanner } from '../components/Primitives';
import { ChangeCard } from '../features/dashboard/ChangeCard';

export function ChangesPage() {
  const query = useQuery(dashboardQuery);
  return (
    <>
      <PageHeading
        eyebrow="MAS / HORIZON SCENARIO"
        title="Change analysis"
        description="Trace each proposed change to its baseline, supporting evidence and prospective control impact."
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
