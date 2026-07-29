/**
 * Reading a Server-Sent Events endpoint.
 *
 * `EventSource` is not usable here: it cannot send an `Authorization` header, and the only
 * ways around that are a token in the query string (which lands in logs and history) or a
 * cookie (which brings CSRF). `fetch` with a `ReadableStream` supports headers, is
 * cancellable via `AbortController`, and unwinds cleanly when the component unmounts.
 *
 * This module is the transport only — framing, auth and the stalled-stream watchdog. What a
 * frame *means* belongs to the hook that asked for it.
 */

import { config } from '../config'
import { useAuthStore } from '../store/auth'

export interface SseFrame {
  /** The `event:` field, or `message` when the server sent none. */
  event: string
  data: unknown
}

/** Thrown when a stream connects but then goes silent; the caller falls back to polling. */
export class StreamSilentError extends Error {
  constructor() {
    super('stream-silent')
    this.name = 'StreamSilentError'
  }
}

/** Split an SSE byte buffer into complete frames, keeping the incomplete tail. */
function splitFrames(buffer: string): { frames: string[]; rest: string } {
  const parts = buffer.split('\n\n')
  return { frames: parts.slice(0, -1), rest: parts[parts.length - 1] }
}

function parseFrame(raw: string): SseFrame | null {
  let event = 'message'
  const data: string[] = []

  for (const line of raw.split('\n')) {
    // Comment frames (": keepalive") carry no data and must not be parsed. They still count
    // as traffic, which is the point: they are what keeps the watchdog below quiet.
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trim())
  }

  if (!data.length) return null
  try {
    return { event, data: JSON.parse(data.join('\n')) }
  } catch {
    return null
  }
}

interface Options {
  signal: AbortSignal
  /** Return `false` to stop reading and close the connection. */
  onFrame: (frame: SseFrame) => boolean | void
}

/**
 * Consume `path` (relative to the gateway) until the server closes it, `onFrame` returns
 * `false`, or the signal aborts.
 *
 * Throws on a stream that cannot be opened, and on one that opens but delivers nothing for
 * `streamSilenceTimeoutMs` — a stream held by a buffering intermediary connects fine and
 * then blocks in `read()` forever, so without a watchdog nothing ever errors and the caller
 * waits on a dead connection for the life of the page.
 */
export async function consumeEventStream(path: string, { signal, onFrame }: Options): Promise<void> {
  const token = useAuthStore.getState().token
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  })

  if (!response.ok || !response.body) {
    throw new Error(`Stream unavailable (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let silenceTimer: ReturnType<typeof setTimeout> | null = null

  // Raced against every read. Cancelling the reader here does NOT abort the caller's
  // controller, so the caller stays free to fall back to polling.
  const silence = () =>
    new Promise<never>((_, reject) => {
      silenceTimer = setTimeout(() => reject(new StreamSilentError()), config.streamSilenceTimeoutMs)
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
    if (done) return

    buffer += decoder.decode(value, { stream: true })
    const { frames, rest } = splitFrames(buffer)
    buffer = rest

    for (const raw of frames) {
      const frame = parseFrame(raw)
      if (!frame) continue
      if (onFrame(frame) === false) {
        await reader.cancel().catch(() => {})
        return
      }
    }
  }
}
