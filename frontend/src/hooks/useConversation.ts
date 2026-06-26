// src/hooks/useConversation.ts
/**
 * Conversation management hook — CRUD on localStorage.
 *
 * Architecture note: all persistence goes through the helpers at the
 * bottom of this file. Swapping localStorage for a server API later
 * only requires changing `loadAll()` and `persistAll()`.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import type { Conversation } from "@/types/conversation";
import type { Message } from "@/types/chat";
import { uuid, now, truncate } from "@/lib/utils";

const STORAGE_KEY = "rag-conversations";
const ACTIVE_KEY = "rag-active-conversation";

// ─── Persistence helpers ───────────────────────────────────────────

function loadAll(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Conversation[]) : [];
  } catch {
    return [];
  }
}

function persistAll(convos: Conversation[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convos));
}

function loadActiveId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACTIVE_KEY);
}

function persistActiveId(id: string) {
  localStorage.setItem(ACTIVE_KEY, id);
}

// ─── Hook ──────────────────────────────────────────────────────────

export function useConversation() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Hydrate from localStorage on mount.
  useEffect(() => {
    const all = loadAll();
    setConversations(all);
    const savedActive = loadActiveId();
    if (savedActive && all.some((c) => c.id === savedActive)) {
      setActiveIdState(savedActive);
    } else if (all.length > 0) {
      setActiveIdState(all[0].id);
    }
  }, []);

  // Persist whenever conversations change.
  useEffect(() => {
    if (conversations.length > 0) persistAll(conversations);
  }, [conversations]);

  // Persist active ID.
  useEffect(() => {
    if (activeId) persistActiveId(activeId);
  }, [activeId]);

  const activeConversation =
    conversations.find((c) => c.id === activeId) ?? null;

  // Filtered list for search.
  const filteredConversations = searchQuery
    ? conversations.filter((c) =>
        c.title.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : conversations;

  const createConversation = useCallback((): Conversation => {
    const convo: Conversation = {
      id: uuid(),
      title: "New conversation",
      messages: [],
      createdAt: now(),
      updatedAt: now(),
    };
    setConversations((prev) => [convo, ...prev]);
    setActiveIdState(convo.id);
    return convo;
  }, []);

  const setActiveId = useCallback((id: string) => {
    setActiveIdState(id);
  }, []);

  const deleteConversation = useCallback(
    (id: string) => {
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        if (activeId === id) {
          setActiveIdState(next.length > 0 ? next[0].id : null);
        }
        if (next.length === 0) {
          localStorage.removeItem(STORAGE_KEY);
        }
        return next;
      });
    },
    [activeId],
  );

  const renameConversation = useCallback((id: string, title: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === id ? { ...c, title, updatedAt: now() } : c,
      ),
    );
  }, []);

  const addMessage = useCallback(
    (conversationId: string, message: Message) => {
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id !== conversationId) return c;
          const updated = {
            ...c,
            messages: [...c.messages, message],
            updatedAt: now(),
          };
          // Auto-title from first user message
          if (
            message.role === "user" &&
            c.messages.length === 0
          ) {
            updated.title = truncate(message.content, 40);
          }
          return updated;
        }),
      );
    },
    [],
  );

  const updateLastAssistantMessage = useCallback(
    (conversationId: string, updater: (msg: Message) => Message) => {
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id !== conversationId) return c;
          const msgs = [...c.messages];
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === "assistant") {
              msgs[i] = updater(msgs[i]);
              break;
            }
          }
          return { ...c, messages: msgs, updatedAt: now() };
        }),
      );
    },
    [],
  );

  const clearMessages = useCallback(
    (conversationId: string) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === conversationId
            ? { ...c, messages: [], title: "New conversation", updatedAt: now() }
            : c,
        ),
      );
    },
    [],
  );

  return {
    conversations: filteredConversations,
    activeConversation,
    activeId,
    searchQuery,
    setSearchQuery,
    createConversation,
    setActiveId,
    deleteConversation,
    renameConversation,
    addMessage,
    updateLastAssistantMessage,
    clearMessages,
  };
}
