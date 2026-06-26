// src/stores/uiStore.ts
/** Global UI state managed by Zustand. */

import { create } from "zustand";

interface UIState {
  /** Whether the mobile sidebar drawer is open. */
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  /** Theme preference. */
  theme: "light" | "dark";
  setTheme: (theme: "light" | "dark") => void;
  toggleTheme: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  theme: "dark",
  setTheme: (theme) => set({ theme }),
  toggleTheme: () =>
    set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
}));
