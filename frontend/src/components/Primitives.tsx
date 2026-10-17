import type { ReactNode } from 'react';
import { AlertCircle, ChevronRight, LoaderCircle, ShieldCheck } from 'lucide-react';
import { ApiError } from '../api/client';

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'teal' | 'amber' | 'red';
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function ProposalBanner() {
  return (
    <div className="proposal-banner">
      <ShieldCheck size={17} aria-hidden="true" />
      <span>
        <strong>PROPOSED — NOT AN IN-FORCE REQUIREMENT</strong>
        <span className="banner-detail">
          Historical 2016 → 2023 scenario. Approved baseline preserved.
        </span>
      </span>
    </div>
  );
}
export function LoadingState({ label = 'Loading your workspace…' }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle className="spin" size={25} />
      <p>{label}</p>
    </div>
  );
}
export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="error-panel" role="alert">
      <AlertCircle size={22} aria-hidden="true" />
      <div>
        <strong>We couldn’t complete that request</strong>
        <p>{error.message}</p>
        {error instanceof ApiError && error.requestId && (
          <small>Reference: {error.requestId}</small>
        )}
        {retry && (
          <button className="button button-secondary" onClick={retry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Trail({ current }: { current: string }) {
  return (
    <div className="breadcrumb">
      Workspace <ChevronRight size={13} /> <span>{current}</span>
    </div>
  );
}
