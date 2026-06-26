// src/hooks/useChatStream.ts
/**
 * Hook that manages SSE-based streaming chat.
 *
 * Encapsulates:
 * - Sending user messages
 * - Streaming assistant responses via postChatStream()
 * - Stop / regenerate controls
 * - Error handling
 */

"use client";

import { useCallback, useRef, useState } from "react";
import type { Message, Citation, SSEEvent } from "@/types/chat";
import { postChatStream } from "@/services/api";
import { uuid, now } from "@/lib/utils";

interface UseChatStreamOptions {
  conversationId: string | null;
  addMessage: (conversationId: string, message: Message) => void;
  updateLastAssistantMessage: (
    conversationId: string,
    updater: (msg: Message) => Message,
  ) => void;
}

export function useChatStream({
  conversationId,
  addMessage,
  updateLastAssistantMessage,
}: UseChatStreamOptions) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const contentRef = useRef("");

  const send = useCallback(
    (query: string) => {
      if (!conversationId || !query.trim() || isGenerating) return;

      setError(null);

      // 1. Add user message
      const userMsg: Message = {
        id: uuid(),
        role: "user",
        content: query.trim(),
        timestamp: now(),
      };
      addMessage(conversationId, userMsg);

      // 2. Add placeholder assistant message
      const assistantMsg: Message = {
        id: uuid(),
        role: "assistant",
        content: "",
        timestamp: now(),
        isStreaming: true,
      };
      addMessage(conversationId, assistantMsg);

      setIsGenerating(true);
      contentRef.current = "";

      // 3. Start SSE stream
      const controller = postChatStream(
        { query: query.trim() },
        (event: SSEEvent) => {
          if (!conversationId) return;

          switch (event.event) {
            case "token":
              contentRef.current += event.content;
              updateLastAssistantMessage(conversationId, (msg) => ({
                ...msg,
                content: contentRef.current,
              }));
              break;

            case "citations":
              updateLastAssistantMessage(conversationId, (msg) => ({
                ...msg,
                citations: event.citations,
              }));
              break;

            case "done":
              updateLastAssistantMessage(conversationId, (msg) => ({
                ...msg,
                isStreaming: false,
              }));
              setIsGenerating(false);
              abortRef.current = null;
              break;

            case "error":
              setError(event.detail);
              updateLastAssistantMessage(conversationId, (msg) => ({
                ...msg,
                content:
                  msg.content ||
                  "An error occurred while generating the response.",
                isStreaming: false,
              }));
              setIsGenerating(false);
              abortRef.current = null;
              break;

            case "retrieval":
              // Could display a "searching X chunks" indicator
              break;
          }
        },
        (err) => {
          setError(err.message);
          if (conversationId) {
            updateLastAssistantMessage(conversationId, (msg) => ({
              ...msg,
              content:
                msg.content || "An error occurred. Please try again.",
              isStreaming: false,
            }));
          }
          setIsGenerating(false);
          abortRef.current = null;
        },
      );

      abortRef.current = controller;
    },
    [conversationId, isGenerating, addMessage, updateLastAssistantMessage],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsGenerating(false);
    if (conversationId) {
      updateLastAssistantMessage(conversationId, (msg) => ({
        ...msg,
        isStreaming: false,
      }));
    }
  }, [conversationId, updateLastAssistantMessage]);

  const regenerate = useCallback(
    (messages: Message[]) => {
      if (!conversationId || isGenerating) return;
      // Find the last user message
      const lastUser = [...messages]
        .reverse()
        .find((m) => m.role === "user");
      if (!lastUser) return;

      // Remove the last assistant message before regenerating
      // (handled by the ChatWindow component which calls this)
      send(lastUser.content);
    },
    [conversationId, isGenerating, send],
  );

  return {
    isGenerating,
    error,
    send,
    stop,
    regenerate,
  };
}
