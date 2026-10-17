import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { request } from '../api/client';

interface CatalogView {
  origin: 'FIRESTORE' | 'LOCAL_SEED';
  catalog: {
    title: string;
    baseline: string;
    comparison: string;
    notice: string;
    steps: { label: string; path: string }[];
  };
}

export function DemoGuide() {
  const query = useQuery({
    queryKey: ['demo-catalog'],
    queryFn: () => request<CatalogView>('/demo-catalog'),
    staleTime: 300_000,
    retry: false,
  });
  if (query.isPending) return <p role="status">Loading the example walkthrough…</p>;
  if (query.error) {
    return (
      <p role="status">
        The example guide is temporarily unavailable. Open Delta Review to continue.
      </p>
    );
  }
  const { catalog, origin } = query.data;
  return (
    <section className="demo-guide" aria-label="Example walkthrough">
      <div className="section-heading">
        <div>
          <p className="eyebrow">
            {origin === 'FIRESTORE' ? 'LIVE FIRESTORE SCENARIO GUIDE' : 'LOCAL SCENARIO GUIDE'}
          </p>
          <h2>{catalog.title}</h2>
        </div>
      </div>
      <p>
        <strong>{catalog.baseline}</strong>
      </p>
      <p>{catalog.comparison}</p>
      <p>{catalog.notice}</p>
      <nav aria-label="Demonstration steps" className="demo-guide-steps">
        {catalog.steps.map((step) => (
          <Link className="button button-secondary" key={step.path} to={step.path}>
            {step.label}
          </Link>
        ))}
      </nav>
    </section>
  );
}
