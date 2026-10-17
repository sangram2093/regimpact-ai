import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Activity,
  ArrowUpRight,
  Check,
  CircleDot,
  GitBranch,
  LayoutDashboard,
  Menu,
  Network,
  RotateCcw,
  ScanLine,
  ShieldCheck,
  X,
  BookOpen,
  FileCheck2,
  MessageSquareText,
  Workflow,
} from 'lucide-react';
import { useReset } from '../api/queries';
import { DemoContext } from '../hooks/demo';
import type { ReviewerRole } from '../types/api';
import { ErrorState, Trail } from './Primitives';

const navigation = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/changes', label: 'Change analysis', icon: ScanLine },
  { to: '/delta-review', label: 'Delta Review', icon: GitBranch },
  { to: '/impact', label: 'Impact lineage', icon: Network },
  { to: '/coverage-gap', label: 'Coverage gaps', icon: CircleDot },
  { to: '/mandates', label: 'Mandates & mappings', icon: FileCheck2 },
  { to: '/sources', label: 'Source register', icon: BookOpen },
  { to: '/ask', label: 'Ask RegImpact', icon: MessageSquareText },
  { to: '/runs', label: 'Workflow runs', icon: Workflow },
];

export function Layout() {
  const [role, setRole] = useState<ReviewerRole>('Regulatory Specialist');
  const [mobileOpen, setMobileOpen] = useState(false);
  const reset = useReset();
  const path = useLocation().pathname;
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [path]);
  const current = navigation.find((item) => path.startsWith(item.to))?.label ?? 'Workspace';
  return (
    <DemoContext.Provider value={{ role, setRole }}>
      <div className="app-shell">
        <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
          <NavLink to="/dashboard" className="brand" onClick={() => setMobileOpen(false)}>
            <span className="brand-mark">
              <GitBranch size={23} strokeWidth={2.2} />
            </span>
            <span>
              RegImpact <b>AI</b>
              <small>BY REGNEXUS AI</small>
            </span>
          </NavLink>
          <button
            className="mobile-close icon-button"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X />
          </button>
          <div className="workspace-label">
            <span className="workspace-icon">RN</span>
            <div>
              RegNexus workspace<small>Regulatory intelligence</small>
            </div>
          </div>
          <p className="nav-label">WORKSPACE</p>
          <nav aria-label="Main navigation">
            {navigation.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={18} />
                <span>{label}</span>
                {label === 'Delta Review' && <span className="nav-dot" />}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="governance-note">
              <ShieldCheck size={20} />
              <strong>Judgment stays human.</strong>
              <p>
                Evidence-led recommendations.
                <br />
                Specialist-authorized decisions.
              </p>
            </div>
            <div className="team-label">
              <span className="team-avatar">RN</span>
              <div>
                RegNexus AI<small>AI Builder Cup 2026</small>
              </div>
              <ArrowUpRight size={15} />
            </div>
          </div>
        </aside>
        {mobileOpen && (
          <button
            className="nav-scrim"
            aria-label="Close navigation overlay"
            onClick={() => setMobileOpen(false)}
          />
        )}
        <div className="main-shell">
          <header className="topbar">
            <div className="topbar-left">
              <button
                className="mobile-toggle icon-button"
                aria-label="Open navigation"
                onClick={() => setMobileOpen(true)}
              >
                <Menu size={21} />
              </button>
              <Trail current={current} />
            </div>
            <div className="topbar-actions">
              <span className="local-mode">
                <span />
                Demonstration workspace
              </span>
              <label className="reviewer-select">
                <span>DEMO REVIEWER ROLE</span>
                <select
                  value={role}
                  onChange={(event) => setRole(event.target.value as ReviewerRole)}
                >
                  <option>Regulatory Specialist</option>
                  <option>Policy Owner</option>
                  <option>Risk Steward</option>
                </select>
              </label>
              <span className="reviewer-avatar" title="Demo reviewer">
                DR
              </span>
            </div>
          </header>
          <main id="main-content">
            <div className="seed-strip">
              <Activity size={14} />
              <span>
                SEED / GOLDEN LABELS{' '}
                <span className="seed-description">
                  · Baseline fixture · No live AI run represented in baseline
                </span>
              </span>
              <button
                className="reset-button"
                onClick={() => reset.mutate()}
                disabled={reset.isPending}
              >
                <RotateCcw size={13} />
                {reset.isPending ? 'Resetting…' : 'Reset demo'}
              </button>
            </div>
            {reset.error && <ErrorState error={reset.error} />}
            {reset.isSuccess && (
              <p className="reset-notice" role="status">
                <Check size={14} />
                Your local scenario decisions have been reset.
              </p>
            )}
            <Outlet />
          </main>
          <footer className="app-footer">
            <span>
              Regulatory content: public MAS sources. Enterprise policies, controls and taxonomies:
              synthetic hackathon data.
            </span>
            <span>Demonstration system · Does not provide legal advice.</span>
          </footer>
        </div>
      </div>
    </DemoContext.Provider>
  );
}
