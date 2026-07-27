import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useMembers, useMemberMutations } from '../../api/projects'
import { errorMessage } from '../../api/errors'
import { Trash2, UserPlus, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'

const ROLE_COLORS: Record<string, string> = {
  owner: 'bg-purple-100 text-purple-800',
  admin: 'bg-blue-100 text-blue-800',
  reviewer: 'bg-green-100 text-green-800',
  analyst: 'bg-yellow-100 text-yellow-700',
  viewer: 'bg-gray-100 text-gray-600',
}

export default function TeamPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ user_email: '', role: 'reviewer' })

  const { data: members = [], isLoading: loading, error: loadError } =
    useMembers(Number(projectId))
  const error = loadError ? errorMessage(loadError, 'Could not load the team') : null
  const memberMutations = useMemberMutations(Number(projectId))

  const handleAdd = async () => {
    if (!form.user_email) { toast.error('An email address is required'); return }
    try {
      await memberMutations.add.mutateAsync(form)
      toast.success('Member added')
      setShowForm(false)
      setForm({ user_email: '', role: 'reviewer' })
    } catch (mutationError) {
      toast.error(errorMessage(mutationError, 'Could not add that member'))
    }
  }

  const handleRoleChange = async (userId: number, role: string) => {
    try {
      await memberMutations.updateRole.mutateAsync({ userId, role })
      toast.success('Role updated')
    } catch (mutationError) {
      toast.error(errorMessage(mutationError, 'Could not update the role'))
    }
  }

  const handleRemove = async (userId: number) => {
    if (!window.confirm('Remove this member?')) return
    try {
      await memberMutations.remove.mutateAsync(userId)
      toast.success('Member removed')
    } catch (mutationError) {
      toast.error(errorMessage(mutationError, 'Could not remove that member'))
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Team</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowForm(!showForm)} className="flex items-center gap-1 text-sm bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700">
            <UserPlus size={14} /> Invite
          </button>
        </div>
      </div>

      {showForm && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">Email</label>
            <input className="border border-gray-300 rounded px-2 py-1 text-sm w-full" value={form.user_email}
              onChange={(e) => setForm({ ...form, user_email: e.target.value })} placeholder="user@example.com" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Role</label>
            <select className="border border-gray-300 rounded px-2 py-1 text-sm" value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {['reviewer', 'analyst', 'admin', 'viewer'].map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <button onClick={handleAdd} className="bg-blue-600 text-white text-sm px-3 py-1 rounded hover:bg-blue-700">Add</button>
          <button onClick={() => setShowForm(false)} className="text-sm text-gray-500">Cancel</button>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700 flex items-center gap-2">
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {loading ? <p className="text-sm text-gray-500">Loading…</p> : members.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p>No team members yet.</p>
          <p className="text-sm mt-1">Click <strong>Invite</strong> to add collaborators.</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-2 text-left font-medium text-gray-600">Member</th>
                <th className="px-4 py-2 text-left font-medium text-gray-600">Role</th>
                <th className="px-4 py-2 text-left font-medium text-gray-600">Joined</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {members.map((m) => (
                <tr key={m.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900">{m.user?.full_name ?? `User #${m.user_id}`}</p>
                    <p className="text-xs text-gray-400">{m.user?.email}</p>
                  </td>
                  <td className="px-4 py-3">
                    {m.role === 'owner' ? (
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${ROLE_COLORS.owner}`}>owner</span>
                    ) : (
                      <select
                        className="border border-gray-300 rounded px-2 py-0.5 text-xs"
                        value={m.role}
                        onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                      >
                        {['admin', 'reviewer', 'analyst', 'viewer'].map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">{new Date(m.joined_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    {m.role !== 'owner' && (
                      <button onClick={() => handleRemove(m.user_id)} className="text-red-400 hover:text-red-600 p-1">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
