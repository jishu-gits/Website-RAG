// src/hooks/useTheme.ts
/**
 * Theme hook — reads/writes to localStorage + toggles the `dark` class on <html>.
 * The Zustand UI store holds the reactive state; this hook syncs it with the DOM.
 */

"use client";

import { useEffect } from "react";
import { useUIStore } from "@/stores/uiStore";

const THEME_KEY = "rag-theme";

export function useTheme() {
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);
  const toggleTheme = useUIStore((s) => s.toggleTheme);

  // On mount: hydrate from localStorage (default dark).
  useEffect(() => {
    const stored = localStorage.getItem(THEME_KEY) as
      | "light"
      | "dark"
      | null;
    if (stored) {
      setTheme(stored);
    }
  }, [setTheme]);

  // Sync DOM class + persist whenever `theme` changes.
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  return { theme, toggleTheme };
}
