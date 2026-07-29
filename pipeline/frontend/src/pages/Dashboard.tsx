import { useState, useEffect, FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Plus, FolderOpen, FileText, CheckSquare, Trash2, FlaskConical, X, BarChart2, Eye } from 'lucide-react'
import toast from 'react-hot-toast'
import { useCreateProject, useDeleteProject, useProjects } from '../api/projects'
import { errorMessage } from '../api/errors'
import { Project } from '../types'
import { useAuthStore } from '../store/auth'

export default function Dashboard() {
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const user = useAuthStore((s) => s.user)

  // The list is owned by the cache; the mutations invalidate it, so no local copy is kept
  // in sync by hand and there is no window where the two disagree.
  const { data: projects = [], isLoading: loading } = useProjects()
  const createProject = useCreateProject()
  const deleteProject = useDeleteProject()
  const creating = createProject.isPending

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await createProject.mutateAsync({ name: name.trim(), description: desc.trim() })
      setShowCreate(false)
      setName('')
      setDesc('')
      toast.success('Project created')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not create the project'))
    }
  }

  const handleDelete = async (id: number, projectName: string) => {
    if (!confirm(`Delete project "${projectName}" and all its data?`)) return
    try {
      await deleteProject.mutateAsync(id)
      toast.success('Project deleted')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the project'))
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">My Projects</h1>
          <p className="muted mt-1">Welcome back, <span className="font-medium text-slate-700">{user?.full_name}</span></p>
        </div>
        <button onClick={() => setShowCreate(true)} className="btn-primary">
          <Plus size={16} />
          New Project
        </button>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md border border-slate-200">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <h2 className="text-base font-semibold text-slate-900">New Research Project</h2>
              <button onClick={() => setShowCreate(false)} className="btn-ghost p-1.5">
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
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
                  placeholder="Brief description of this research project…"
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                />
              </div>
              <p className="text-xs text-slate-400">
                A default food-preservation schema will be applied. You can customize it in Schema settings.
              </p>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary flex-1 justify-center">
                  Cancel
                </button>
                <button type="submit" className="btn-primary flex-1 justify-center" disabled={creating}>
                  {creating ? 'Creating…' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm text-slate-500">Loading projects…</p>
          </div>
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mb-5">
            <FlaskConical size={28} className="text-blue-400" />
          </div>
          <h3 className="text-base font-semibold text-slate-900 mb-1">No projects yet</h3>
          <p className="text-sm text-slate-500 mb-6 max-w-xs">Create your first project to start extracting structured data from scientific papers using AI.</p>
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus size={16} /> Create First Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {projects.map((p) => (
            <div
              key={p.id}
              className="bg-white border border-slate-200 rounded-xl shadow-sm hover:shadow-md hover:border-slate-300 transition-all duration-200 group flex flex-col"
            >
              <div className="p-5 flex-1">
                <div className="flex items-start justify-between mb-3">
                  <div className="w-9 h-9 bg-blue-50 rounded-lg flex items-center justify-center shrink-0">
                    <FolderOpen size={16} className="text-blue-600" />
                  </div>
                  <button
                    onClick={() => handleDelete(p.id, p.name)}
                    className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                    title="Delete project"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <Link
                  to={`/projects/${p.id}`}
                  className="block font-semibold text-slate-900 hover:text-blue-600 transition-colors mt-2 mb-1 line-clamp-1"
                >
                  {p.name}
                </Link>
                {p.description && (
                  <p className="text-slate-500 text-xs line-clamp-2 mb-3">{p.description}</p>
                )}
                <div className="flex items-center gap-4 text-xs text-slate-400 mt-3 pt-3 border-t border-slate-100">
                  <span className="flex items-center gap-1.5">
                    <FileText size={12} />
                    <span>{p.paper_count ?? 0} papers</span>
                  </span>
                  {p.your_role && p.your_role !== 'owner' && (
                    <span className="flex items-center gap-1.5">
                      <CheckSquare size={12} />
                      <span>{p.your_role}</span>
                    </span>
                  )}
                </div>
              </div>
              {/* The Review and Analytics shortcuts here pointed at two pages deleted with
                  the flat-extraction path, and had been resolving to the catch-all redirect
                  ever since. */}
              <div className="px-5 pb-4 flex gap-2">
                <Link to={`/projects/${p.id}`} className="btn-primary text-xs py-1.5 px-3 flex-1 justify-center">
                  Open
                </Link>
                <Link
                  to={`/projects/${p.id}/extracted`}
                  className="btn-secondary text-xs py-1.5 px-3"
                  title="Extracted data"
                >
                  <Eye size={12} />
                </Link>
                <Link
                  to={`/projects/${p.id}/database`}
                  className="btn-secondary text-xs py-1.5 px-3"
                  title="Scientific database"
                >
                  <BarChart2 size={12} />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
