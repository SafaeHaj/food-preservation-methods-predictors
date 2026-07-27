/** Authentication calls. Not cached: the token is owned by the auth store, not the cache. */

import { post, get } from './client'

export interface AuthResponse {
  access_token: string
  token_type: string
  user: { id: number; email: string; full_name: string }
}

export const login = (email: string, password: string) =>
  post<AuthResponse>('/auth/login', { email, password })

export const register = (email: string, full_name: string, password: string) =>
  post<AuthResponse>('/auth/register', { email, full_name, password })

export const me = () => get<{ id: number; email: string; full_name: string }>('/auth/me')
