import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { ChangesPage } from './pages/ChangesPage';
import { ChangeDetailPage } from './pages/ChangeDetailPage';
import { DeltaReviewPage } from './pages/DeltaReviewPage';
import { ImpactPage } from './pages/ImpactPage';
import { CoveragePage } from './pages/CoveragePage';
import { SourcesPage } from './pages/SourcesPage';
import { MandatesPage } from './pages/MandatesPage';
import { AskPage } from './pages/AskPage';
import { RunsPage } from './pages/RunsPage';

export function App() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="changes" element={<ChangesPage />} />
          <Route path="changes/:id" element={<ChangeDetailPage />} />
          <Route path="delta-review" element={<DeltaReviewPage />} />
          <Route path="impact" element={<ImpactPage />} />
          <Route path="impact/:id" element={<ImpactPage />} />
          <Route path="coverage-gap" element={<CoveragePage />} />
          <Route path="sources" element={<SourcesPage />} />
          <Route path="mandates" element={<MandatesPage />} />
          <Route path="mandates/:id" element={<MandatesPage />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="runs" element={<RunsPage />} />
          <Route
            path="*"
            element={
              <div className="panel">
                <h1>Page not found</h1>
                <p>Use the workspace navigation to return to your scenario.</p>
              </div>
            }
          />
        </Route>
      </Routes>
    </>
  );
}
