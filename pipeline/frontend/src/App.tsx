import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/auth'

// Auth pages
import Login from './pages/Login'
import Register from './pages/Register'

// Top-level layout (Dashboard)
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'

// Project layout (dark sidebar, full-height)
import ProjectLayout from './pages/ProjectLayout'
import ProjectView from './pages/ProjectView'

// Legacy pages
import Upload from './pages/Upload'
import SchemaPage from './pages/SchemaPage'
import Review from './pages/Review'
import Analytics from './pages/Analytics'

// Canonical project pages
import StudiesPage from './pages/project/StudiesPage'
import ExperimentsPage from './pages/project/ExperimentsPage'
import DatasetPage from './pages/project/DatasetPage'
import NormalizationPage from './pages/project/NormalizationPage'
import MissingDataPage from './pages/project/MissingDataPage'
import TrajectoriesPage from './pages/project/TrajectoriesPage'
import ModelLabPage from './pages/project/ModelLabPage'
import ModelTrainingPage from './pages/project/ModelTrainingPage'
import ModelGuidePage from './pages/project/ModelGuidePage'
import ImputationsPage from './pages/project/ImputationsPage'
import TreatmentsPage from './pages/project/TreatmentsPage'
import ThresholdShelfLifePage from './pages/project/ThresholdShelfLifePage'
import ExtractionJobsPage from './pages/project/ExtractionJobsPage'
import ExtractionWorkspacePage from './pages/project/ExtractionWorkspacePage'
import PPChart2TablePage from './pages/project/PPChart2TablePage'
import ValidationPage from './pages/project/ValidationPage'
import AuditHistoryPage from './pages/project/AuditHistoryPage'
import ExportPage from './pages/project/ExportPage'
import TeamPage from './pages/project/TeamPage'
import ProjectSettingsPage from './pages/project/ProjectSettingsPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Dashboard — uses top-nav Layout */}
      <Route
        path="/"
        element={<RequireAuth><Layout /></RequireAuth>}
      >
        <Route index element={<Dashboard />} />
      </Route>

      {/* Project section — full-height dark-sidebar layout, no global header */}
      <Route
        path="/projects/:projectId"
        element={<RequireAuth><ProjectLayout /></RequireAuth>}
      >
        <Route index element={<ProjectView />} />

        {/* Legacy */}
        <Route path="upload" element={<Upload />} />
        <Route path="schema" element={<SchemaPage />} />
        <Route path="review" element={<Review />} />
        <Route path="analytics" element={<Analytics />} />

        {/* Canonical scientific data */}
        <Route path="studies" element={<StudiesPage />} />
        <Route path="experiments" element={<ExperimentsPage />} />
        <Route path="dataset" element={<DatasetPage />} />

        {/* Data quality */}
        <Route path="normalization" element={<NormalizationPage />} />
        <Route path="missing" element={<MissingDataPage />} />

        {/* Analysis */}
        <Route path="trajectories" element={<TrajectoriesPage />} />
        <Route path="models" element={<ModelLabPage />} />
        <Route path="model-lab" element={<ModelTrainingPage />} />
        <Route path="model-lab/guide/:modelId" element={<ModelGuidePage />} />
        <Route path="imputations" element={<ImputationsPage />} />
        <Route path="treatments" element={<TreatmentsPage />} />
        <Route path="thresholds" element={<ThresholdShelfLifePage />} />

        {/* Extraction workspace */}
        <Route path="papers/:paperId/workspace" element={<ExtractionWorkspacePage />} />

        {/* PP-Chart2Table — must be scoped to a specific paper */}
        <Route path="papers/:paperId/chart2table" element={<PPChart2TablePage />} />

        {/* Validation */}
        <Route path="validation" element={<ValidationPage />} />

        {/* Operations */}
        <Route path="jobs" element={<ExtractionJobsPage />} />
        <Route path="audit" element={<AuditHistoryPage />} />
        <Route path="export" element={<ExportPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="settings" element={<ProjectSettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
