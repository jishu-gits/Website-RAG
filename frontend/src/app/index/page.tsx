export const dynamic = "force-dynamic";
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
const { postIngest, getStatus } = await import("@/services/api");

export default function IndexWebsitePage() {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<"idle" | "crawling" | "embedding" | "success" | "error">("idle");
  const [message, setMessage] = useState("Ready");
  const [errorMessage, setErrorMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();

    if (!trimmed) {
      setErrorMessage("Please enter a valid website URL.");
      setStatus("error");
      return;
    }

    try {
      new URL(trimmed);
      if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
        throw new Error();
      }
    } catch {
      setErrorMessage("Please enter a valid website URL.");
      setStatus("error");
      return;
    }

    setErrorMessage("");
    setStatus("crawling");
    setMessage("Crawling website...");

    // Since the backend `/api/ingest` is a single blocking endpoint, 
    // we use a timeout to simulate the transition for better UX.
    const timer = setTimeout(() => {
      setStatus("embedding");
      setMessage("Creating embeddings...");
    }, 4000);

    try {
      await postIngest([trimmed], 2);
      clearTimeout(timer);

      setStatus("success");

      try {
        const stats = await getStatus();
        setMessage(`✅ Website indexed successfully. Indexed vectors: ${stats.vector_store_size}`);
      } catch (statusErr) {
        // Fallback if status fetch fails
        setMessage(`✅ Website indexed successfully.`);
      }

    } catch (err) {
      clearTimeout(timer);
      setStatus("error");
      setMessage("❌ Failed to index website.");
      setErrorMessage(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-sm p-6 space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-bold tracking-tight">Index Website</h1>
          <p className="text-sm text-muted-foreground">
            Enter a website URL to crawl and add it to the knowledge base.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            type="url"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (status === "error") {
                setStatus("idle");
                setMessage("Ready");
                setErrorMessage("");
              }
            }}
            disabled={status === "crawling" || status === "embedding"}
            className="w-full"
            required
          />
          <Button
            type="submit"
            className="w-full"
            disabled={status === "crawling" || status === "embedding"}
          >
            Index Website
          </Button>
        </form>

        <div className="text-center space-y-2">
          <p className="text-sm font-medium">
            {message}
          </p>
          {status === "error" && errorMessage && (
            <p className="text-xs text-destructive bg-destructive/10 p-2 rounded">
              {errorMessage}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
