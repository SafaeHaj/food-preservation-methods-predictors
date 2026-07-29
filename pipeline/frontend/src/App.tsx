/**
 * Routes.
 *
 * Every project page is code-split. Previously all page modules were imported eagerly, so
 * opening the extraction workspace parsed and evaluated the dataset browser and the audit
 * log too — module-level work for screens the user never opened.
 *
 * Thirteen pages went with the parallel scientific hierarchy they read: studies,
 * experiments, treatments, observations, trajectories, kinetic fits, normalization,
 * missing-data, imputations, thresholds, the CSV-upload model lab and the snapshot export.
 * What they showed now lives in two screens — Extracted Data and the Scientific Database —
 * reading the extraction output directly.
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

const ExtractionJobsPage = lazy(() => import('./pages/project/ExtractionJobsPage'))
const ExtractionWorkspacePage = lazy(() => import('./pages/project/ExtractionWorkspacePage'))
const ExtractedDataPage = lazy(() => import('./pages/project/ExtractedDataPage'))
const PPChart2TablePage = lazy(() => import('./pages/project/PPChart2TablePage'))
const ValidationPage = lazy(() => import('./pages/project/ValidationPage'))
const ScientificDatabasePage = lazy(() => import('./pages/project/ScientificDatabasePage'))
const ModelLabPage = lazy(() => import('./pages/project/ModelLabPage'))
const PredictionPage = lazy(() => import('./pages/project/PredictionPage'))
const AuditHistoryPage = lazy(() => import('./pages/project/AuditHistoryPage'))
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

          {/* Extraction pipeline */}
          <Route path="upload" element={<Upload />} />
          <Route path="jobs" element={<ExtractionJobsPage />} />
          <Route path="extracted" element={<ExtractedDataPage />} />
          <Route path="papers/:paperId/workspace" element={<ExtractionWorkspacePage />} />
          <Route path="papers/:paperId/chart2table" element={<PPChart2TablePage />} />
          <Route path="validation" element={<ValidationPage />} />

          {/* Scientific database */}
          <Route path="database" element={<ScientificDatabasePage />} />

          {/* Model lab */}
          <Route path="model-lab" element={<ModelLabPage />} />
          <Route path="prediction" element={<PredictionPage />} />

          {/* Administration */}
          <Route path="team" element={<TeamPage />} />
          <Route path="settings" element={<ProjectSettingsPage />} />
          <Route path="audit" element={<AuditHistoryPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
