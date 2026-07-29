/**
 * Keep a project's job list live, without polling and without refetching.
 *
 * `useJobStream` follows a job whose id the caller already has. A page that *lists* jobs has
 * a different problem: it does not know which ids to watch, one of them finishing is not the
 * end of the story, and a job started elsewhere — another tab, the upload flow, a teammate —
 * must appear on its own. Subscribing per row answers none of that and spends a connection
 * per running job against the browser's six-per-origin limit.
 *
 * So this subscribes to the list itself. Each frame carries the whole page of jobs and is
 * written straight into the react-query cache under the same key `useJobs` reads, so the
 * component re-renders from a push with no request of its own. The server only sends a frame
 * when something actually changed.
 */

import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { config } from '../config'
import { get } from '../api/client'
import { consumeEventStream } from '../api/sse'
import { keys } from '../api/keys'
import type { JobFilters } from '../api/jobs'
import type { Job } from '../types'

/**
 * @param filters must be the *same* filters passed to `useJobs`, so both address the same
 *   cache entry — a key spelled differently here would update a row nothing renders.
 */
export function useJobsStream(filters: JobFilters, options: { enabled?: boolean } = {}) {
  const queryClient = useQueryClient()
  const [live, setLive] = useState(false)

  const enabled = options.enabled !== false && Number.isFinite(filters.project_id)
  // Serialised so a fresh object literal each render does not restart the stream.
  const filterKey = JSON.stringify(filters)

  useEffect(() => {
    if (!enabled) return

    const active = JSON.parse(filterKey) as JobFilters
    const controller = new AbortController()
    // Set when the server says this subscription can never succeed (access revoked, project
    // gone). Anything else that ends the stream is worth retrying by polling; this is not.
    let fatal = false

    const query = new URLSearchParams(
      Object.entries(active)
        .filter(([, value]) => value !== undefined && value !== null)
        .map(([name, value]) => [name, String(value)]),
    )

    const write = (jobs: Job[]) => {
      queryClient.setQueryData(keys.jobs.list(active), jobs)
    }

    const consume = () =>
      consumeEventStream(`/jobs/events?${query}`, {
        signal: controller.signal,
        onFrame: ({ event, data }) => {
          if (event === 'jobs') {
            write(data as Job[])
            setLive(true)
            return
          }
          if (event === 'error') fatal = true
          // `expired` is the server retiring a long-lived connection rather than a failure,
          // but either way this stream is over.
          if (event === 'error' || event === 'expired') return false
        },
      })

    /** Safety net for an environment that cannot hold the stream open. */
    const poll = async () => {
      while (!controller.signal.aborted) {
        try {
          write(await get<Job[]>('/jobs', active))
        } catch {
          if (controller.signal.aborted) return
        }
        await new Promise((resolve) => setTimeout(resolve, config.jobPollFallbackMs))
      }
    }

    /** Any end to the stream that is not a teardown leaves the page on the poll. */
    const degrade = () => {
      if (controller.signal.aborted || fatal) return
      setLive(false)
      return poll()
    }

    consume()
      .then(degrade, degrade)
      .catch(() => {
        /* aborted during teardown */
      })

    return () => {
      controller.abort()
      setLive(false)
    }
  }, [enabled, filterKey, queryClient])

  /** True while the push channel is actually delivering, for an honest "live" indicator. */
  return { live }
}
