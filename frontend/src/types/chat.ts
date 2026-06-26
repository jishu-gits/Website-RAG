// src/types/chat.ts
/** Core chat domain types used across the application. */

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations?: Citation[];
  isStreaming?: boolean;
  liked?: boolean;
  disliked?: boolean;
}

export interface Citation {
  url: string;
  title: string;
  score?: number;
}

/** SSE event shapes from the backend. */
export type SSEEvent =
  | { event: "retrieval"; chunks_used: number }
  | { event: "token"; content: string }
  | { event: "citations"; citations: Citation[] }
  | { event: "done"; has_sufficient_context: boolean }
  | { event: "error"; detail: string };

/** Request body sent to POST /api/chat */
export interface ChatRequest {
  query: string;
  top_k?: number;
  use_mmr?: boolean;
  mmr_lambda?: number;
  stream?: boolean;
  filters?: Record<string, unknown>;
}

/** Non-streaming response from POST /api/chat */
export interface ChatResponse {
  query: string;
  answer: string;
  citations: Citation[];
  has_sufficient_context: boolean;
  chunks_used: number;
}
