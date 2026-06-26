"use client";

import * as React from "react";
import {
  MessageSquare,
  Plus,
  Trash2,
  Edit2,
  Search,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn, formatDate } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ScrollArea } from "@/components/ui/ScrollArea";
import { Sheet, SheetContent } from "@/components/ui/Sheet";
import { useConversation } from "@/hooks/useConversation";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/Dialog";

interface SidebarProps {
  isMobile?: boolean;
}

function SidebarContent({ isMobile }: SidebarProps) {
  const {
    conversations,
    activeId,
    searchQuery,
    setSearchQuery,
    createConversation,
    setActiveId,
    deleteConversation,
    renameConversation,
  } = useConversation();
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);

  const [renamingId, setRenamingId] = React.useState<string | null>(null);
  const [renameValue, setRenameValue] = React.useState("");

  const handleCreate = () => {
    createConversation();
    if (isMobile) setSidebarOpen(false);
  };

  const handleSelect = (id: string) => {
    setActiveId(id);
    if (isMobile) setSidebarOpen(false);
  };

  const handleRenameSubmit = () => {
    if (renamingId && renameValue.trim()) {
      renameConversation(renamingId, renameValue.trim());
    }
    setRenamingId(null);
  };

  return (
    <div className="flex flex-col h-full bg-card dark:bg-card/50 border-r border-border">
      {/* New Chat Button */}
      <div className="p-4">
        <Button
          onClick={handleCreate}
          className="w-full justify-start gap-2 h-11"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>

      {/* Search */}
      <div className="px-4 pb-4">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search..."
            className="pl-9 h-9 bg-background/50"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Conversation List */}
      <ScrollArea className="flex-1">
        <div className="px-2 space-y-1 pb-4">
          <AnimatePresence initial={false}>
            {conversations.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-sm text-center text-muted-foreground py-8"
              >
                No conversations found.
              </motion.div>
            ) : (
              conversations.map((c) => (
                <motion.div
                  key={c.id}
                  layout
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <button
                    onClick={() => handleSelect(c.id)}
                    className={cn(
                      "w-full group flex flex-col items-start gap-1 p-3 text-sm rounded-lg transition-colors hover:bg-accent hover:text-accent-foreground text-left",
                      activeId === c.id
                        ? "bg-accent/80 font-medium"
                        : "text-muted-foreground"
                    )}
                  >
                    <div className="flex items-center justify-between w-full">
                      <div className="flex items-center gap-2 truncate">
                        <MessageSquare className="h-4 w-4 shrink-0" />
                        <span className="truncate">{c.title}</span>
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 rounded hover:bg-background/80"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRenamingId(c.id);
                            setRenameValue(c.title);
                          }}
                        >
                          <Edit2 className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 rounded hover:bg-destructive/10 hover:text-destructive"
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteConversation(c.id);
                          }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                    <span className="text-[10px] text-muted-foreground/70 pl-6">
                      {formatDate(c.updatedAt)}
                    </span>
                  </button>
                </motion.div>
              ))
            )}
          </AnimatePresence>
        </div>
      </ScrollArea>

      {/* Rename Dialog */}
      <Dialog
        open={!!renamingId}
        onOpenChange={(open) => !open && setRenamingId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename Conversation</DialogTitle>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleRenameSubmit();
            }}
            autoFocus
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRenamingId(null)}>
              Cancel
            </Button>
            <Button onClick={handleRenameSubmit}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function Sidebar() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-[280px] flex-col border-r border-border shrink-0 z-10 bg-card">
        <SidebarContent />
      </aside>

      {/* Mobile Sidebar */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="p-0 w-[80%] max-w-[300px]">
          <SidebarContent isMobile />
        </SheetContent>
      </Sheet>
    </>
  );
}
