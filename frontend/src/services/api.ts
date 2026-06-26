// src/services/api.ts
/**
 * API service layer — thin wrappers around the FastAPI backend.
 * All business-logic-bearing fetch calls live here, not in components.
 */

import type { ChatRequest, ChatResponse, SSEEvent } from "@/types/chat";
import { env } from "@/lib/env";

const BASE = env.NEXT_PUBLIC_API_URL;

/** POST /api/chat (non-streaming). */
export async function postChat(body: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, stream: false }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Chat request failed (${res.status}): ${detail}`);
  }
  return res.json();
}

/**
 * POST /api/chat (streaming via SSE).
 *
 * Returns an AbortController so the caller can cancel mid-stream,
 * and invokes `onEvent` for each parsed SSE event.
 */
export function postChatStream(
  body: ChatRequest,
  onEvent: (event: SSEEvent) => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, stream: true }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`Stream request failed (${res.status}): ${detail}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

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
            onEvent(event);
          } catch {
            // Ignore malformed JSON lines
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  })();

  return controller;
}

/** GET /api/status */
export async function getStatus(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/status`);
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

/** POST /api/ingest */
export async function postIngest(
  urls: string[],
  maxDepth = 2,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls, max_depth: maxDepth }),
  });
  if (!res.ok) throw new Error("Ingest failed");
  return res.json();
}
