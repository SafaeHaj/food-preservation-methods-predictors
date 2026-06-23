import { useState, useEffect, FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Plus, FolderOpen, FileText, CheckSquare, Trash2, FlaskConical } from 'lucide-react'
import toast from 'react-hot-toast'
import { projectsApi } from '../services/api'
import { Project } from '../types'
import { useAuthStore } from '../store/auth'

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const user = useAuthStore((s) => s.user)

  const load = async () => {
    try {
      const data = await projectsApi.list()
      setProjects(data)
    } catch {
      toast.error('Failed to load projects')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    try {
      const project = await projectsApi.create({ name: name.trim(), description: desc.trim() })
      setProjects((prev) => [project, ...prev])
      setShowCreate(false)
      setName('')
      setDesc('')
      toast.success('Project created')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to create project')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: number, projectName: string) => {
    if (!confirm(`Delete project "${projectName}" and all its data?`)) return
    try {
      await projectsApi.delete(id)
      setProjects((prev) => prev.filter((p) => p.id !== id))
      toast.success('Project deleted')
    } catch {
      toast.error('Failed to delete project')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Projects</h1>
          <p className="text-slate-400 text-sm mt-0.5">Welcome back, {user?.full_name}</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary">
          <Plus size={16} />
          New Project
        </button>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="card w-full max-w-md">
            <h2 className="text-lg font-semibold mb-4">New Research Project</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="label">Project Name *</label>
                <input
                  className="input"
                  placeholder="e.g. Antimicrobial Meat Study 2024"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="label">Description</label>
                <textarea
                  className="input resize-none h-20"
                  placeholder="Brief description of this project..."
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                />
              </div>
              <p className="text-xs text-slate-500">
                A default food-preservation schema will be applied. You can customize it later.
              </p>
              <div className="flex gap-3 justify-end">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-500 py-20">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="text-center py-20">
          <FlaskConical size={48} className="text-slate-700 mx-auto mb-4" />
          <h3 className="text-slate-400 font-medium mb-2">No projects yet</h3>
          <p className="text-slate-600 text-sm">Create a project to start extracting data from scientific papers.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((p) => (
            <div key={p.id} className="card hover:border-slate-700 transition-colors group">
              <div className="flex items-start justify-between mb-3">
                <Link
                  to={`/projects/${p.id}`}
                  className="font-semibold text-slate-100 hover:text-blue-400 transition-colors flex-1 min-w-0 pr-2 truncate"
                >
                  {p.name}
                </Link>
                <button
                  onClick={() => handleDelete(p.id, p.name)}
                  className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 transition-all shrink-0"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              {p.description && (
                <p className="text-slate-500 text-sm mb-3 line-clamp-2">{p.description}</p>
              )}
              <div className="flex items-center gap-4 text-xs text-slate-500">
                <span className="flex items-center gap-1">
                  <FileText size={12} />
                  {p.paper_count} papers
                </span>
                <span className="flex items-center gap-1">
                  <CheckSquare size={12} />
                  {p.row_count} rows
                </span>
              </div>
              <div className="mt-4 flex gap-2">
                <Link to={`/projects/${p.id}`} className="btn-primary text-xs py-1.5 px-3">
                  Open
                </Link>
                <Link to={`/projects/${p.id}/review`} className="btn-secondary text-xs py-1.5 px-3">
                  Review
                </Link>
                <Link to={`/projects/${p.id}/analytics`} className="btn-secondary text-xs py-1.5 px-3">
                  Analytics
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
