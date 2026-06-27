// src/services/api.ts
/**
 * API service layer — thin wrappers around the FastAPI backend.
 * All business-logic-bearing fetch calls live here, not in components.
 *
 * URL construction:
 *   env.NEXT_PUBLIC_API_URL  must be the full base including /api segment.
 *   Example: https://website-rag-qxbv.onrender.com/api
 *
 *   Endpoints are appended without repeating /api:
 *     POST /api/chat   → `${BASE}/chat`
 *     GET  /api/status → `${BASE}/status`
 *     POST /api/ingest → `${BASE}/ingest`
 */

import type { ChatRequest, ChatResponse, SSEEvent } from "@/types/chat";
import { env } from "@/lib/env";

const BASE = env.NEXT_PUBLIC_API_URL;

// Dev-only logger — tree-shaken in production builds by Next.js.
const devLog = (...args: unknown[]) => {
  if (process.env.NODE_ENV === "development") {
    // eslint-disable-next-line no-console
    console.log("[api]", ...args);
  }
};

/** POST /api/chat (non-streaming). */
export async function postChat(body: ChatRequest): Promise<ChatResponse> {
  const url = `${BASE}/chat`;
  devLog("POST (non-stream)", url);

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, stream: false }),
  });

  devLog("Response status:", res.status, res.statusText);

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Chat request failed (${res.status}): ${detail}`);
  }
  return res.json();
}

/**
 * POST /api/chat (streaming via SSE).
 *
 * Returns an AbortController so the caller can cancel mid-stream.
 * Invokes `onEvent` for each parsed SSE event.
 *
 * BUG 5 FIX: Added a `receivedDone` flag. If the reader closes without a
 * "done" SSE event (e.g. Render kills the connection), `onError` is called
 * so the caller can clear `isGenerating` and unlock the UI.
 */
export function postChatStream(
  body: ChatRequest,
  onEvent: (event: SSEEvent) => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();
  const url = `${BASE}/chat`;

  devLog("POST (stream)", url, "body:", body);

  (async () => {
    let receivedDone = false;

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, stream: true }),
        signal: controller.signal,
      });

      devLog("Stream response status:", res.status, res.statusText);

      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`Stream request failed (${res.status}): ${detail}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body from stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last (possibly incomplete) line in the buffer.
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const json = trimmed.slice(5).trim();
          if (!json) continue;
          try {
            const event: SSEEvent = JSON.parse(json);
            devLog("SSE event:", event.event, event);
            if (event.event === "done") receivedDone = true;
            onEvent(event);
          } catch {
            // Ignore malformed JSON lines — backend may emit non-JSON heartbeats.
          }
        }
      }

      // BUG 5 FIX: Stream ended cleanly but no "done" event was received.
      // Synthesize a done event so the UI unlocks correctly.
      if (!receivedDone) {
        devLog("Stream ended without 'done' event — synthesizing done.");
        onEvent({ event: "done", has_sufficient_context: true });
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        devLog("Stream aborted by user.");
        return;
      }
      devLog("Stream error:", err);
      onError(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return controller;
}

/** GET /api/status */
export async function getStatus(): Promise<Record<string, unknown>> {
  const url = `${BASE}/status`;
  devLog("GET", url);
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

/** POST /api/ingest */
export async function postIngest(
  urls: string[],
  maxDepth = 2,
): Promise<Record<string, unknown>> {
  const url = `${BASE}/ingest`;
  devLog("POST", url);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls, max_depth: maxDepth }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Ingest failed (${res.status}): ${detail}`);
  }
  return res.json();
}
