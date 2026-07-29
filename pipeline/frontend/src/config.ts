/**
 * Frontend configuration, read from the build environment.
 *
 * Page sizes, cache lifetimes and stream timings were previously literals scattered across
 * 25 page components — `limit: 200` here, `limit: 500` there, `setInterval(..., 2500)` in
 * one file and `8000` in another — so tuning any of them meant hunting through the UI.
 */

function num(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

/** Gateway origin, without a trailing slash. Empty means same-origin. */
const apiOrigin = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

export const config = {
  apiOrigin,

  /** Gateway origin. Empty means same-origin, which is what the dev proxy serves. */
  apiBaseUrl: apiOrigin ? `${apiOrigin}/api` : '/api',

  /**
   * How long a fetched resource is considered fresh. Within this window a remount reads
   * the cache instead of issuing a request — the single change that removes most of the
   * redundant traffic, since navigating back to a page no longer refetches it.
   */
  staleTimeMs: num(import.meta.env.VITE_STALE_TIME_MS, 30_000),

  /** How long an unused cache entry is kept before eviction. */
  cacheTimeMs: num(import.meta.env.VITE_CACHE_TIME_MS, 5 * 60_000),

  /** Page sizes for list endpoints. */
  pageSize: {
    assets: num(import.meta.env.VITE_PAGE_SIZE_ASSETS, 100),
    observations: num(import.meta.env.VITE_PAGE_SIZE_OBSERVATIONS, 200),
    default: num(import.meta.env.VITE_PAGE_SIZE_DEFAULT, 100),
  },

  /**
   * Fallback poll interval for a job whose event stream could not be opened (a proxy that
   * buffers SSE, for instance). The stream is the normal path; this is the safety net.
   */
  jobPollFallbackMs: num(import.meta.env.VITE_JOB_POLL_FALLBACK_MS, 3000),

  /**
   * If an opened stream produces no bytes for this long, treat it as buffered-and-dead and
   * fall back to polling. Must exceed the server's keepalive (15s) so a healthy but quiet
   * stream is never mistaken for a stalled one. Without this, a stream that connects but is
   * held by a buffering intermediary never errors, so the "running" state never resolves.
   */
  streamSilenceTimeoutMs: num(import.meta.env.VITE_STREAM_SILENCE_TIMEOUT_MS, 25_000),
} as const

/**
 * Resolve a server-minted binary URL against the gateway origin.
 *
 * The extraction service signs *paths* (`/api/projects/1/papers/2/assets/3/image?exp=…&sig=…`)
 * because the signature must cover exactly what the server will verify, and it does not know
 * which origin the SPA is served from. A relative path is then resolved by the browser
 * against the *page's* origin — which is the SPA, not the API. Wherever the two differ, as
 * they do under `VITE_API_URL`, every `<img src>`, `<a href>` and CSV fetch silently 404s or
 * 500s while the JSON calls beside them work, because those go through axios and its
 * `baseURL`. Hence: everything that leaves the API layer carries an absolute URL.
 */
export function assetUrl<T extends string | null | undefined>(path: T): T {
  if (!path || !apiOrigin) return path
  // Already absolute (or a data: URI): leave it alone.
  if (/^[a-z][a-z0-9+.-]*:/i.test(path) || path.startsWith('//')) return path
  return `${apiOrigin}${path.startsWith('/') ? '' : '/'}${path}` as T
}
