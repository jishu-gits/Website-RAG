// frontend/src/app/layout.tsx
import "./globals.css";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";
import { ThemeProvider } from "@/providers/ThemeProvider";
import { ConversationProvider } from "@/providers/ConversationProvider";
import { ToastProvider } from "@/components/ToastProvider";
import { Header } from "@/components/Header";
import { Sidebar } from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata = {
  title: "Website RAG Assistant",
  description: "A Retrieval‑Augmented Generation assistant for website content.",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body className="bg-background text-foreground antialiased selection:bg-primary/20 selection:text-primary min-h-screen flex overflow-hidden">
        <ThemeProvider>
          {/*
            ConversationProvider must wrap both <Sidebar> and {children} (ChatWindow).
            BUG 1 FIX: Previously, Sidebar and ChatWindow each called useConversation()
            independently, creating two separate React useState trees. ChatWindow's copy
            always had activeId=null, causing send() to early-return with no fetch.
            With a single Provider here, both components consume the exact same state.
          */}
          <ConversationProvider>
            {/* Main Layout Wrapper */}
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0">
              <Header />
              <main className="flex-1 flex flex-col overflow-hidden relative">
                {children}
              </main>
            </div>
          </ConversationProvider>
          <ToastProvider />
        </ThemeProvider>
      </body>
    </html>
  );
}
