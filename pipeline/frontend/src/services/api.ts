import axios from 'axios'
import { useAuthStore } from '../store/auth'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// Auth
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }).then((r) => r.data),
  register: (email: string, full_name: string, password: string) =>
    api.post('/auth/register', { email, full_name, password }).then((r) => r.data),
  me: () => api.get('/auth/me').then((r) => r.data),
}

// Projects
export const projectsApi = {
  list: () => api.get('/projects').then((r) => r.data),
  get: (id: number) => api.get(`/projects/${id}`).then((r) => r.data),
  create: (data: { name: string; description?: string; schema_fields?: unknown[] }) =>
    api.post('/projects', data).then((r) => r.data),
  update: (id: number, data: Partial<{ name: string; description: string; schema_fields: unknown[] }>) =>
    api.patch(`/projects/${id}`, data).then((r) => r.data),
  delete: (id: number) => api.delete(`/projects/${id}`),
}

// Papers
export const papersApi = {
  list: (projectId: number) => api.get(`/projects/${projectId}/papers`).then((r) => r.data),
  upload: (projectId: number, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return api.post(`/projects/${projectId}/papers`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
  delete: (projectId: number, paperId: number) =>
    api.delete(`/projects/${projectId}/papers/${paperId}`),
}

// Extraction
export const extractionApi = {
  extractOne: (projectId: number, paperId: number) =>
    api.post(`/projects/${projectId}/extract/${paperId}`).then((r) => r.data),
  extractAll: (projectId: number) =>
    api.post(`/projects/${projectId}/extract`).then((r) => r.data),
}

// Review rows
export const reviewApi = {
  list: (projectId: number, params?: { status?: string; paper_id?: number; skip?: number; limit?: number }) =>
    api.get(`/projects/${projectId}/rows`, { params }).then((r) => r.data),
  update: (projectId: number, rowId: number, data: { data?: Record<string, unknown>; status?: string; reviewer_note?: string }) =>
    api.patch(`/projects/${projectId}/rows/${rowId}`, data).then((r) => r.data),
  bulkStatus: (projectId: number, row_ids: number[], status: string) =>
    api.post(`/projects/${projectId}/rows/bulk-status`, { row_ids, status }).then((r) => r.data),
  delete: (projectId: number, rowId: number) =>
    api.delete(`/projects/${projectId}/rows/${rowId}`),
}

// Analytics
export const analyticsApi = {
  get: (projectId: number) => api.get(`/projects/${projectId}/analytics`).then((r) => r.data),
}

// Export
export const exportApi = {
  excel: (projectId: number) =>
    api.get(`/projects/${projectId}/export/excel`, { responseType: 'blob' }).then((r) => {
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a')
      const cd = r.headers['content-disposition'] || ''
      const match = cd.match(/filename="?([^"]+)"?/)
      a.download = match ? match[1] : 'export.xlsx'
      a.href = url
      a.click()
      URL.revokeObjectURL(url)
    }),
}

// Schema inference
export const schemaApi = {
  infer: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/schema/infer', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
}
