/**
 * The single axios instance. Everything HTTP goes through it.
 */

import axios from 'axios'
import { config } from '../config'
import { useAuthStore } from '../store/auth'
import { toApiError } from './errors'

export const client = axios.create({ baseURL: config.apiBaseUrl })

client.interceptors.request.use((request) => {
  const token = useAuthStore.getState().token
  if (token) request.headers.Authorization = `Bearer ${token}`
  return request
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const apiError = toApiError(error)

    // An expired or revoked token: drop it and return to the login screen. Checked on the
    // status rather than the code so a 401 from any layer is handled.
    if (apiError.status === 401) {
      useAuthStore.getState().logout()
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }

    // Reject with the normalized error so every consumer — queries, mutations, error
    // boundaries — sees one type.
    return Promise.reject(apiError)
  },
)

/** GET returning the response body. */
export const get = <T>(url: string, params?: object): Promise<T> =>
  client.get<T>(url, { params }).then((response) => response.data)

export const post = <T>(url: string, body?: unknown): Promise<T> =>
  client.post<T>(url, body).then((response) => response.data)

export const patch = <T>(url: string, body?: unknown): Promise<T> =>
  client.patch<T>(url, body).then((response) => response.data)

export const del = (url: string): Promise<void> => client.delete(url).then(() => undefined)

/** POST multipart/form-data. */
export const postForm = <T>(url: string, form: FormData): Promise<T> =>
  client
    .post<T>(url, form, { headers: { 'Content-Type': 'multipart/form-data' } })
    .then((response) => response.data)

/**
 * Download a binary response as a file.
 *
 * Centralised because the blob/object-URL/anchor-click dance was written out twice, and
 * both copies leaked the object URL when the filename header was missing.
 */
export async function download(url: string, fallbackName: string): Promise<void> {
  const response = await client.get(url, { responseType: 'blob' })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const match = disposition.match(/filename="?([^"]+)"?/)

  const objectUrl = URL.createObjectURL(response.data)
  try {
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = match ? match[1] : fallbackName
    anchor.click()
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

