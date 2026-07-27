import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useDeleteProject, useProject, useUpdateProject } from '../../api/projects'
import { errorMessage } from '../../api/errors'
import toast from 'react-hot-toast'

export default function ProjectSettingsPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', description: '' })
  const [saving, setSaving] = useState(false)

  const { data: project } = useProject(Number(projectId))
  const updateProject = useUpdateProject(Number(projectId))
  const deleteProject = useDeleteProject()

  // Seed the editable form once the project arrives. The query owns the server value; this
  // state owns the in-progress edit, which is the one thing the cache should not hold.
  useEffect(() => {
    if (project) setForm({ name: project.name, description: project.description })
  }, [project])

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateProject.mutateAsync(form)
      toast.success('Project updated')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not update the project'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Delete this project and all its data? This cannot be undone.')) return
    try {
      await deleteProject.mutateAsync(Number(projectId))
      toast.success('Project deleted')
      navigate('/')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the project'))
    }
  }

  if (!project) return <p className="text-sm text-gray-500">Loading…</p>

  return (
    <div className="max-w-lg">
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Project Settings</h1>

      <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Project name</label>
          <input className="border border-gray-300 rounded px-3 py-2 text-sm w-full"
            value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
          <textarea className="border border-gray-300 rounded px-3 py-2 text-sm w-full" rows={3}
            value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <button onClick={handleSave} disabled={saving}
          className="bg-blue-600 text-white text-sm px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50">
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>

      <div className="mt-8 bg-red-50 border border-red-200 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-red-800 mb-2">Danger Zone</h2>
        <p className="text-sm text-red-700 mb-3">Deleting the project removes all studies, experiments, and observations permanently.</p>
        <button onClick={handleDelete} className="bg-red-600 text-white text-sm px-4 py-2 rounded hover:bg-red-700">
          Delete project
        </button>
      </div>
    </div>
  )
}
