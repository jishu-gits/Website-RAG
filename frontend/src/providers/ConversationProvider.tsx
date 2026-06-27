// src/providers/ConversationProvider.tsx
/**
 * ConversationProvider — single source of truth for all conversation state.
 *
 * Architecture fix: Previously, both <Sidebar /> and <ChatWindow /> called
 * useConversation() independently, creating two separate React useState trees.
 * That meant ChatWindow.activeConversation was always null when Sidebar created
 * a conversation, causing send() to silently short-circuit with zero fetch requests.
 *
 * This provider is mounted once in layout.tsx and exposes the entire conversation
 * API via useConversationContext(). All consumers share the exact same state instance.
 */

"use client";

import * as React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Conversation } from "@/types/conversation";
import type { Message } from "@/types/chat";
import { uuid, now, truncate } from "@/lib/utils";

// ─── Persistence keys ──────────────────────────────────────────────

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
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convos));
}

function loadActiveId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACTIVE_KEY);
}

function persistActiveId(id: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACTIVE_KEY, id);
}

// ─── Context shape ──────────────────────────────────────────────────

interface ConversationContextValue {
  conversations: Conversation[];
  activeConversation: Conversation | null;
  activeId: string | null;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  createConversation: () => Conversation;
  setActiveId: (id: string) => void;
  deleteConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => void;
  addMessage: (conversationId: string, message: Message) => void;
  updateLastAssistantMessage: (
    conversationId: string,
    updater: (msg: Message) => Message,
  ) => void;
  clearMessages: (conversationId: string) => void;
}

const ConversationContext = React.createContext<ConversationContextValue | null>(
  null,
);

// ─── Provider ──────────────────────────────────────────────────────

export function ConversationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Track whether initial hydration has completed so we only auto-create once.
  const hydratedRef = useRef(false);

  // ── Hydrate + auto-create default conversation ──────────────────
  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;

    const all = loadAll();
    const savedActive = loadActiveId();

    if (all.length === 0) {
      // BUG 2 FIX: First launch — auto-create a default conversation so
      // activeConversation is never null and send() always has a valid ID.
      if (process.env.NODE_ENV === "development") {
        console.log("[ConversationProvider] No conversations in localStorage — creating default.");
      }
      const defaultConvo: Conversation = {
        id: uuid(),
        title: "New conversation",
        messages: [],
        createdAt: now(),
        updatedAt: now(),
      };
      setConversations([defaultConvo]);
      setActiveIdState(defaultConvo.id);
      persistAll([defaultConvo]);
      persistActiveId(defaultConvo.id);
    } else {
      setConversations(all);
      if (savedActive && all.some((c) => c.id === savedActive)) {
        setActiveIdState(savedActive);
      } else {
        setActiveIdState(all[0].id);
      }
    }
  }, []);

  // ── Persist whenever conversations change (skip initial empty state) ──
  useEffect(() => {
    if (!hydratedRef.current) return;
    if (conversations.length > 0) persistAll(conversations);
  }, [conversations]);

  // ── Persist active ID ───────────────────────────────────────────
  useEffect(() => {
    if (activeId) persistActiveId(activeId);
  }, [activeId]);

  // ── Derived state ───────────────────────────────────────────────
  const activeConversation =
    conversations.find((c) => c.id === activeId) ?? null;

  if (process.env.NODE_ENV === "development" && typeof window !== "undefined") {
    // Non-reactive diagnostic — fires on every render, intentional for audit purposes.
    // Remove after confirming the fix works.
    console.debug("[ConversationProvider] activeId:", activeId, "| activeConversation:", activeConversation?.id ?? "null", "| conversations:", conversations.length);
  }

  const filteredConversations = searchQuery
    ? conversations.filter((c) =>
        c.title.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : conversations;

  // ── Actions ─────────────────────────────────────────────────────

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
          if (next.length > 0) {
            setActiveIdState(next[0].id);
          } else {
            // Auto-create a new conversation so activeId is never null after delete.
            const replacement: Conversation = {
              id: uuid(),
              title: "New conversation",
              messages: [],
              createdAt: now(),
              updatedAt: now(),
            };
            setActiveIdState(replacement.id);
            return [replacement];
          }
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
          if (message.role === "user" && c.messages.length === 0) {
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

  const clearMessages = useCallback((conversationId: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === conversationId
          ? { ...c, messages: [], title: "New conversation", updatedAt: now() }
          : c,
      ),
    );
  }, []);

  const value: ConversationContextValue = {
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

  return (
    <ConversationContext.Provider value={value}>
      {children}
    </ConversationContext.Provider>
  );
}

// ─── Consumer hook ──────────────────────────────────────────────────

/**
 * Use this instead of useConversation() everywhere.
 * Throws if called outside <ConversationProvider> so errors are never silent.
 */
export function useConversationContext(): ConversationContextValue {
  const ctx = React.useContext(ConversationContext);
  if (!ctx) {
    throw new Error(
      "useConversationContext() must be called inside <ConversationProvider>. " +
        "Check that ConversationProvider wraps your layout in app/layout.tsx.",
    );
  }
  return ctx;
}
