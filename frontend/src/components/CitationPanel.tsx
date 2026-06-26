"use client";

import { ExternalLink } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/Accordion";
import type { Citation } from "@/types/chat";

export function CitationPanel({ citations }: { citations: Citation[] }) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="mt-4 w-full">
      <Accordion type="single" collapsible className="w-full">
        <AccordionItem value="sources" className="border-none">
          <AccordionTrigger className="py-2 text-xs text-muted-foreground hover:text-foreground hover:no-underline flex-none justify-start gap-2">
            View Sources ({citations.length})
          </AccordionTrigger>
          <AccordionContent>
            <div className="grid gap-2 pt-2">
              {citations.map((c, i) => (
                <a
                  key={i}
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between p-3 rounded-lg border bg-card/50 hover:bg-accent/50 transition-colors group text-left"
                >
                  <div className="flex flex-col min-w-0 pr-4">
                    <span className="font-medium text-sm truncate text-foreground">
                      {c.title || new URL(c.url).hostname}
                    </span>
                    <span className="text-xs text-muted-foreground truncate">
                      {c.url}
                    </span>
                  </div>
                  <ExternalLink className="h-4 w-4 text-muted-foreground opacity-50 group-hover:opacity-100 shrink-0" />
                </a>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
