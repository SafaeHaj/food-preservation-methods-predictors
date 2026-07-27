/**
 * Routes.
 *
 * Every project page is code-split. Previously all 25 page modules were imported eagerly,
 * so opening the extraction workspace parsed and evaluated the model lab, the dataset
 * browser and the audit log too — module-level work for screens the user never opened.
 *
 * The legacy Review and Analytics pages are gone with the flat-extraction path they read.
 */

import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from './store/auth'

// Auth pages load eagerly: one of them is the first thing an unauthenticated visitor sees,
// and a spinner before the login form is worse than the few kilobytes it saves.
import Login from './pages/Login'
import Register from './pages/Register'

import Layout from './components/Layout'
import ProjectLayout from './pages/ProjectLayout'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const ProjectView = lazy(() => import('./pages/ProjectView'))
const Upload = lazy(() => import('./pages/Upload'))

const StudiesPage = lazy(() => import('./pages/project/StudiesPage'))
const ExperimentsPage = lazy(() => import('./pages/project/ExperimentsPage'))
const DatasetPage = lazy(() => import('./pages/project/DatasetPage'))
const NormalizationPage = lazy(() => import('./pages/project/NormalizationPage'))
const MissingDataPage = lazy(() => import('./pages/project/MissingDataPage'))
const TrajectoriesPage = lazy(() => import('./pages/project/TrajectoriesPage'))
const ModelLabPage = lazy(() => import('./pages/project/ModelLabPage'))
const ModelTrainingPage = lazy(() => import('./pages/project/ModelTrainingPage'))
const ModelGuidePage = lazy(() => import('./pages/project/ModelGuidePage'))
const ImputationsPage = lazy(() => import('./pages/project/ImputationsPage'))
const TreatmentsPage = lazy(() => import('./pages/project/TreatmentsPage'))
const ThresholdShelfLifePage = lazy(() => import('./pages/project/ThresholdShelfLifePage'))
const ExtractionJobsPage = lazy(() => import('./pages/project/ExtractionJobsPage'))
const ExtractionWorkspacePage = lazy(() => import('./pages/project/ExtractionWorkspacePage'))
const ExtractedDataPage = lazy(() => import('./pages/project/ExtractedDataPage'))
const PPChart2TablePage = lazy(() => import('./pages/project/PPChart2TablePage'))
const ValidationPage = lazy(() => import('./pages/project/ValidationPage'))
const AuditHistoryPage = lazy(() => import('./pages/project/AuditHistoryPage'))
const ExportPage = lazy(() => import('./pages/project/ExportPage'))
const TeamPage = lazy(() => import('./pages/project/TeamPage'))
const ProjectSettingsPage = lazy(() => import('./pages/project/ProjectSettingsPage'))

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((state) => state.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function PageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route path="/" element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Dashboard />} />
        </Route>

        <Route
          path="/projects/:projectId"
          element={<RequireAuth><ProjectLayout /></RequireAuth>}
        >
          <Route index element={<ProjectView />} />

          {/* Extraction */}
          <Route path="upload" element={<Upload />} />
          <Route path="jobs" element={<ExtractionJobsPage />} />
          <Route path="papers/:paperId/workspace" element={<ExtractionWorkspacePage />} />
          <Route path="papers/:paperId/chart2table" element={<PPChart2TablePage />} />
          <Route path="validation" element={<ValidationPage />} />
          <Route path="extracted" element={<ExtractedDataPage />} />

          {/* Scientific database */}
          <Route path="studies" element={<StudiesPage />} />
          <Route path="experiments" element={<ExperimentsPage />} />
          <Route path="treatments" element={<TreatmentsPage />} />
          <Route path="dataset" element={<DatasetPage />} />

          {/* Data quality */}
          <Route path="normalization" element={<NormalizationPage />} />
          <Route path="missing" element={<MissingDataPage />} />
          <Route path="imputations" element={<ImputationsPage />} />

          {/* Analysis */}
          <Route path="trajectories" element={<TrajectoriesPage />} />
          <Route path="models" element={<ModelLabPage />} />
          <Route path="model-lab" element={<ModelTrainingPage />} />
          <Route path="model-lab/guide/:modelId" element={<ModelGuidePage />} />
          <Route path="thresholds" element={<ThresholdShelfLifePage />} />

          {/* Operations */}
          <Route path="audit" element={<AuditHistoryPage />} />
          <Route path="export" element={<ExportPage />} />
          <Route path="team" element={<TeamPage />} />
          <Route path="settings" element={<ProjectSettingsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
