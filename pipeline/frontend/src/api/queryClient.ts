/**
 * The shared QueryClient.
 *
 * The defaults here are what turn off most of the redundant traffic the app used to make:
 * a stale time so a remount reads the cache, no refetch on window focus, and no retry on
 * errors that will never succeed on a second attempt.
 */

import { QueryClient } from '@tanstack/react-query'
import { config } from '../config'
import { ApiError } from './errors'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: config.staleTimeMs,
      gcTime: config.cacheTimeMs,
      // Navigating back to a tab is not a reason to refetch everything; the stale time
      // already governs freshness.
      refetchOnWindowFocus: false,
      refetchOnMount: false,
      retry: (failureCount, error) => {
        // Retrying a 404 or a 403 just repeats the same answer more slowly.
        if (error instanceof ApiError && !error.isTransient) return false
        return failureCount < 2
      },
    },
    mutations: {
      // A mutation is a user action: it either worked or it did not, and silently retrying
      // risks applying it twice.
      retry: false,
    },
  },
})
