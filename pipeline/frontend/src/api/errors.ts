/**
 * One error shape for the whole app.
 *
 * Every service now answers failures with the same envelope
 * (`shared/error_handlers.py`), so the ~20 hand-written
 * `err.response?.data?.detail ?? 'Something failed'` expressions scattered through the
 * pages collapse into one parser and one message helper.
 */

export interface ApiErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
  request_id?: string
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>
  readonly requestId?: string

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details ?? {}
    this.requestId = body.request_id
  }

  /** True when retrying the same request could plausibly succeed. */
  get isTransient(): boolean {
    return this.status >= 500 || this.code === 'upstream_unavailable'
  }
}

/** Normalize anything thrown by axios into an `ApiError`. */
export function toApiError(error: unknown): ApiError {
  const response = (error as { response?: { status: number; data?: unknown } })?.response

  if (response?.data && typeof response.data === 'object' && 'error' in response.data) {
    return new ApiError(response.status, (response.data as { error: ApiErrorBody }).error)
  }

  if (response) {
    // A non-enveloped failure: an infrastructure layer (proxy, load balancer) answered
    // rather than one of our services.
    return new ApiError(response.status, {
      code: 'http_error',
      message: `Request failed (${response.status})`,
    })
  }

  return new ApiError(0, {
    code: 'network_error',
    message: 'Could not reach the server. Check your connection and try again.',
  })
}

/** The message to show a user for any thrown value. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return fallback
}
