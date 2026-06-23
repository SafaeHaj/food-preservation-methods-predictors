import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/auth'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import ProjectView from './pages/ProjectView'
import Upload from './pages/Upload'
import SchemaPage from './pages/SchemaPage'
import Review from './pages/Review'
import Analytics from './pages/Analytics'
import Layout from './components/Layout'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="projects/:projectId" element={<ProjectView />} />
        <Route path="projects/:projectId/upload" element={<Upload />} />
        <Route path="projects/:projectId/schema" element={<SchemaPage />} />
        <Route path="projects/:projectId/review" element={<Review />} />
        <Route path="projects/:projectId/analytics" element={<Analytics />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
