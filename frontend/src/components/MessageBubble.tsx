"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import {
  Copy,
  Check,
  RotateCw,
  ThumbsUp,
  ThumbsDown,
  User,
  Bot,
} from "lucide-react";
import { motion } from "framer-motion";

import { cn, copyToClipboard } from "@/lib/utils";
import type { Message } from "@/types/chat";
import { Button } from "@/components/ui/Button";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/Tooltip";
import { CitationPanel } from "@/components/CitationPanel";
import { TypingIndicator } from "@/components/TypingIndicator";
import { fadeInUp } from "@/animations/motion";

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: () => void;
  isLast?: boolean;
}

export const MessageBubble = React.memo(
  function MessageBubble({ message, onRegenerate, isLast }: MessageBubbleProps) {
    const isUser = message.role === "user";
    const [copied, setCopied] = React.useState(false);
    const [liked, setLiked] = React.useState(message.liked || false);
    const [disliked, setDisliked] = React.useState(message.disliked || false);

    const handleCopy = async () => {
      if (message.content) {
        const success = await copyToClipboard(message.content);
        if (success) {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }
      }
    };

    return (
      <motion.div
        variants={fadeInUp}
        initial="hidden"
        animate="visible"
        layout
        className={cn(
          "flex w-full gap-4 py-6 px-4 md:px-6 hover:bg-black/5 dark:hover:bg-white/5 transition-colors group",
          isUser ? "" : "bg-muted/30"
        )}
      >
        {/* Avatar */}
        <div
          className={cn(
            "flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-lg shadow-sm border",
            isUser
              ? "bg-secondary text-secondary-foreground"
              : "gradient-primary text-white border-none"
          )}
        >
          {isUser ? <User className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
        </div>

        {/* Content */}
        <div className="flex-1 space-y-2 overflow-hidden min-w-0">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-sm">
              {isUser ? "You" : "RAG Assistant"}
            </span>
          </div>

          <div className="prose-chat text-foreground max-w-none break-words">
            {message.isStreaming && !message.content ? (
              <TypingIndicator />
            ) : (
              <ReactMarkdown
                rehypePlugins={[rehypeRaw, rehypeHighlight as any]}
                components={{
                  a: ({ node, ...props }) => (
                    <a target="_blank" rel="noopener noreferrer" {...props} />
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            )}
          </div>

          {/* Citations */}
          {!isUser && message.citations && message.citations.length > 0 && (
            <CitationPanel citations={message.citations} />
          )}

          {/* Action Toolbar */}
          {!isUser && !message.isStreaming && (
            <div className="flex items-center gap-1 pt-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <TooltipProvider delayDuration={300}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 rounded-md"
                      onClick={handleCopy}
                    >
                      {copied ? (
                        <Check className="h-4 w-4 text-green-500" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Copy</TooltipContent>
                </Tooltip>

                {isLast && onRegenerate && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 rounded-md"
                        onClick={onRegenerate}
                      >
                        <RotateCw className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Regenerate</TooltipContent>
                  </Tooltip>
                )}

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className={cn(
                        "h-8 w-8 rounded-md",
                        liked && "text-primary bg-primary/10"
                      )}
                      onClick={() => {
                        setLiked(!liked);
                        setDisliked(false);
                      }}
                    >
                      <ThumbsUp className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Good response</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className={cn(
                        "h-8 w-8 rounded-md",
                        disliked && "text-destructive bg-destructive/10"
                      )}
                      onClick={() => {
                        setDisliked(!disliked);
                        setLiked(false);
                      }}
                    >
                      <ThumbsDown className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Bad response</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          )}
        </div>
      </motion.div>
    );
  }
);
