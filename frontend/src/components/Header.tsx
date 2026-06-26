"use client";

import { Menu } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useUIStore } from "@/stores/uiStore";

export function Header() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  return (
    <header className="sticky top-0 z-40 w-full glass border-b border-border/50">
      <div className="flex h-14 items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleSidebar}
            className="md:hidden"
            aria-label="Toggle sidebar"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center text-white font-bold shadow-sm">
              RAG
            </div>
            <h1 className="font-semibold text-foreground hidden sm:block tracking-tight">
              Website RAG Assistant
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
