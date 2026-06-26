// src/types/conversation.ts
/** Conversation model for localStorage persistence. */

import type { Message } from "./chat";

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
}

/** Shape stored in localStorage under key "rag-conversations". */
export type ConversationStore = Conversation[];
