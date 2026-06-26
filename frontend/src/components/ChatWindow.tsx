"use client";

import * as React from "react";
import { Send, Square, ArrowDown, Trash2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useConversation } from "@/hooks/useConversation";
import { useChatStream } from "@/hooks/useChatStream";
import { MessageBubble } from "@/components/MessageBubble";
import { Button } from "@/components/ui/Button";
import { ScrollArea } from "@/components/ui/ScrollArea";
import { cn } from "@/lib/utils";

export function ChatWindow() {
  const {
    activeConversation,
    addMessage,
    updateLastAssistantMessage,
    clearMessages,
  } = useConversation();

  const { isGenerating, send, stop, regenerate } = useChatStream({
    conversationId: activeConversation?.id ?? null,
    addMessage,
    updateLastAssistantMessage,
  });

  const [input, setInput] = React.useState("");
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = React.useState(false);
  const viewportRef = React.useRef<HTMLDivElement>(null);

  const messages = activeConversation?.messages ?? [];

  // Auto-scroll logic
  const scrollToBottom = React.useCallback((smooth = true) => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({
        behavior: smooth ? "smooth" : "auto",
        block: "end",
      });
    }
  }, []);

  React.useEffect(() => {
    // If generating, aggressively scroll down unless user scrolled up
    if (isGenerating && !showScrollBottom) {
      scrollToBottom(true);
    }
  }, [messages, isGenerating, showScrollBottom, scrollToBottom]);

  // Initial scroll
  React.useEffect(() => {
    scrollToBottom(false);
  }, [activeConversation?.id, scrollToBottom]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
    setShowScrollBottom(!isAtBottom);
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isGenerating) return;
    send(input);
    setInput("");
    scrollToBottom();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleRegenerate = () => {
    // To regenerate, we remove the last assistant message and resend the last user message
    // (useChatStream handles resending, we just pass the messages)
    if (activeConversation) {
      regenerate(messages);
    }
  };

  return (
    <div className="flex flex-col h-full relative bg-background">
      {/* Messages Area */}
      <ScrollArea
        className="flex-1"
        onScrollCapture={handleScroll}
        ref={viewportRef}
      >
        <div className="max-w-3xl mx-auto w-full pb-32 pt-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-[50vh] text-center px-4">
              <div className="w-16 h-16 rounded-2xl gradient-primary flex items-center justify-center mb-6 shadow-xl">
                <span className="text-3xl text-white font-bold">RAG</span>
              </div>
              <h2 className="text-2xl font-semibold mb-2">
                How can I help you today?
              </h2>
              <p className="text-muted-foreground max-w-md">
                I can search the indexed documentation and answer your questions
                with precise source citations.
              </p>
            </div>
          ) : (
            <div className="flex flex-col pb-4">
              <AnimatePresence initial={false}>
                {messages.map((m, idx) => (
                  <MessageBubble
                    key={m.id}
                    message={m}
                    isLast={idx === messages.length - 1}
                    onRegenerate={
                      idx === messages.length - 1 && m.role === "assistant"
                        ? handleRegenerate
                        : undefined
                    }
                  />
                ))}
              </AnimatePresence>
              <div ref={scrollRef} className="h-px" />
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Floating Scroll to Bottom */}
      <AnimatePresence>
        {showScrollBottom && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-28 right-8 z-10"
          >
            <Button
              variant="secondary"
              size="icon"
              className="rounded-full shadow-lg h-10 w-10 bg-background border"
              onClick={() => scrollToBottom()}
            >
              <ArrowDown className="h-5 w-5" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input Area */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-background via-background to-transparent pt-10 pb-4 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto w-full relative">
          <form
            onSubmit={handleSubmit}
            className="relative flex items-end w-full glass-strong rounded-2xl border p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 transition-shadow"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything..."
              className="max-h-60 min-h-[44px] w-full resize-none bg-transparent px-3 py-3 text-sm focus:outline-none scrollbar-thin"
              rows={1}
              style={{
                height: "44px",
                height: `${Math.min(
                  240,
                  Math.max(44, input.split("\n").length * 24 + 20)
                )}px`,
              }}
            />
            <div className="flex items-center gap-2 pr-1 pb-1">
              {messages.length > 0 && !isGenerating && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 text-muted-foreground hover:text-destructive shrink-0 hidden sm:flex"
                  onClick={() =>
                    activeConversation && clearMessages(activeConversation.id)
                  }
                  title="Clear chat"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
              {isGenerating ? (
                <Button
                  type="button"
                  variant="default"
                  size="icon"
                  className="h-9 w-9 shrink-0 bg-primary/20 text-primary hover:bg-primary/30"
                  onClick={stop}
                  title="Stop generating"
                >
                  <Square className="h-4 w-4 fill-current" />
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="icon"
                  className="h-9 w-9 shrink-0 rounded-xl"
                  disabled={!input.trim()}
                >
                  <Send className="h-4 w-4" />
                  <span className="sr-only">Send message</span>
                </Button>
              )}
            </div>
          </form>
          <div className="text-center mt-2">
            <span className="text-[10px] text-muted-foreground">
              AI responses can be inaccurate. Always verify source citations.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
