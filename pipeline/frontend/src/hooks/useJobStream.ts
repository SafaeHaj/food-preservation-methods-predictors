/**
 * Follow one job's progress over Server-Sent Events.
 *
 * This replaces every `setInterval` in the app. The extraction workspace polled a status
 * endpoint every 2.5s *and* refetched all 200 assets on each tick; the jobs page polled
 * every 8s forever; the project view polled every 5s whether or not anything was running.
 * None of them stopped reliably on unmount.
 *
 * `EventSource` is not usable here: it cannot send an `Authorization` header, and the only
 * ways around that are a token in the query string (which lands in logs and history) or a
 * cookie (which brings CSRF). `fetch` with a `ReadableStream` supports headers, is
 * cancellable via `AbortController`, and unwinds cleanly when the component unmounts.
 *
 * A stream that cannot be established falls back to polling `GET /jobs/{id}` so a
 * buffering proxy degrades the experience rather than breaking it.
 */

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { config } from '../config'
import { keys } from '../api/keys'
import { useAuthStore } from '../store/auth'

export interface JobProgress {
  job_id: number
  status: string
  progress: number
  current_step: string
  error: string | null
  result: Record<string, unknown> | null
}

export const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled', 'partial_success']

export const isTerminal = (status?: string): boolean =>
  !!status && TERMINAL_STATUSES.includes(status)

interface Options {
  /** Invalidated once the job reaches a terminal state, so dependent views refetch once. */
  invalidateOnComplete?: readonly (readonly unknown[])[]
  onComplete?: (progress: JobProgress) => void
  onError?: (message: string) => void
}

/** Split an SSE byte stream into complete `event:`/`data:` frames. */
function parseFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split('\n\n')
  return { frames: parts.slice(0, -1), rest: parts[parts.length - 1] }
}

function frameData(frame: string): JobProgress | null {
  // Comment frames (": keepalive") carry no data and must not be parsed.
  const dataLine = frame.split('\n').find((line) => line.startsWith('data:'))
  if (!dataLine) return null
  try {
    return JSON.parse(dataLine.slice(5).trim()) as JobProgress
  } catch {
    return null
  }
}

export function useJobStream(jobId: number | null | undefined, options: Options = {}) {
  const [progress, setProgress] = useState<JobProgress | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Held in refs so changing a callback does not tear down and restart the stream.
  const optionsRef = useRef(options)
  optionsRef.current = options

  useEffect(() => {
    if (!jobId) {
      setProgress(null)
      return
    }

    const controller = new AbortController()
    let finished = false

    const settle = (final: JobProgress) => {
      if (finished) return
      finished = true
      // One invalidation at the end, not a refetch per tick: the results only exist once
      // the job is done, so fetching them during the run is pure waste.
      for (const key of optionsRef.current.invalidateOnComplete ?? []) {
        queryClient.invalidateQueries({ queryKey: key as unknown[] })
      }
      queryClient.invalidateQueries({ queryKey: keys.jobs.all() })
      optionsRef.current.onComplete?.(final)
      if (final.status === 'failed') {
        optionsRef.current.onError?.(final.error ?? 'The job failed')
      }
    }

    const consume = async () => {
      const token = useAuthStore.getState().token
      const response = await fetch(`${config.apiBaseUrl}/jobs/${jobId}/events`, {
        headers: {
          Accept: 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        throw new Error(`Stream unavailable (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      // Watchdog: a stream held open by a buffering intermediary connects fine but never
      // delivers a byte, so `reader.read()` blocks forever and nothing ever errors. Race
      // each read against a silence timeout; on silence, cancel the reader (which does NOT
      // abort the effect's controller) and throw so the outer catch falls back to polling.
      // Any bytes — a progress frame or a keepalive comment — reset the timer.
      let silenceTimer: ReturnType<typeof setTimeout> | null = null
      const silence = () =>
        new Promise<never>((_, reject) => {
          silenceTimer = setTimeout(
            () => reject(new Error('stream-silent')),
            config.streamSilenceTimeoutMs,
          )
        })

      for (;;) {
        let result: ReadableStreamReadResult<Uint8Array>
        try {
          result = await Promise.race([reader.read(), silence()])
        } catch (error) {
          if (silenceTimer) clearTimeout(silenceTimer)
          await reader.cancel().catch(() => {})
          throw error
        }
        if (silenceTimer) clearTimeout(silenceTimer)

        const { done, value } = result
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const { frames, rest } = parseFrames(buffer)
        buffer = rest

        for (const frame of frames) {
          const data = frameData(frame)
          if (!data) continue
          setProgress(data)
          if (isTerminal(data.status)) {
            settle(data)
            return
          }
        }
      }
    }

    /** Safety net for environments where the stream cannot be held open. */
    const poll = async () => {
      while (!controller.signal.aborted && !finished) {
        try {
          const token = useAuthStore.getState().token
          const response = await fetch(`${config.apiBaseUrl}/jobs/${jobId}`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            signal: controller.signal,
          })
          if (response.ok) {
            const job = await response.json()
            const snapshot: JobProgress = {
              job_id: job.id,
              status: job.status,
              progress: job.progress ?? 0,
              current_step: job.current_step ?? '',
              error: job.error_message || null,
              result: job.result ?? null,
            }
            setProgress(snapshot)
            if (isTerminal(snapshot.status)) {
              settle(snapshot)
              return
            }
          }
        } catch {
          if (controller.signal.aborted) return
        }
        await new Promise((resolve) => setTimeout(resolve, config.jobPollFallbackMs))
      }
    }

    consume()
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setStreamError(error instanceof Error ? error.message : 'Stream failed')
        return poll()
      })
      .catch(() => {
        /* aborted during teardown */
      })

    // Aborting on unmount is the whole point: navigating away from a running extraction
    // must close the connection, not leave it running for the rest of the session.
    return () => controller.abort()
  }, [jobId, queryClient])

  return {
    progress,
    streamError,
    isRunning: !!progress && !isTerminal(progress.status),
    isComplete: progress?.status === 'completed',
    isFailed: progress?.status === 'failed',
  }
}
