"use client";

import * as React from "react";
import { useTheme } from "@/hooks/useTheme";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // useTheme already initializes the theme class and localStorage logic
  useTheme();

  return <>{children}</>;
}
