/**
 * Frontend environment variable validation.
 *
 * BUG 3 FIX: Previously this silently fell back to "/api" when NEXT_PUBLIC_API_URL
 * was not set. In production on Vercel, that fallback was a relative path with no
 * rewrite active (vercel.json doesn't exist), meaning every fetch hit a 404 Next.js
 * API route handler that doesn't exist.
 *
 * Rules:
 *  - In production (server-side build), NEXT_PUBLIC_API_URL is REQUIRED. Missing it throws.
 *  - In development, it falls back to http://localhost:8000/api with a warning.
 *  - The URL must NOT have a trailing slash (api.ts appends /chat, /status, etc.)
 *  - The URL must already include /api (e.g. https://backend.onrender.com/api)
 *    because api.ts constructs: BASE + "/chat" → .../api/chat
 */

const getApiUrl = (): string => {
  const raw = process.env.NEXT_PUBLIC_API_URL;

  if (!raw) {
    if (process.env.NODE_ENV === "production" && typeof window === "undefined") {
      // Server-side in production: crash loudly so the build log is unambiguous.
      throw new Error(
        "[env] NEXT_PUBLIC_API_URL is not set. " +
          "Set it in Vercel Environment Variables to your Render backend URL, e.g.: " +
          "https://your-app.onrender.com/api",
      );
    }
    // Client-side production or development: warn and fall back to localhost.
    console.warn(
      "[env] ⚠️  NEXT_PUBLIC_API_URL is not set. " +
        "Falling back to http://localhost:8000/api — this will fail in production.",
    );
    return "http://localhost:8000/api";
  }

  // Strip trailing slash to prevent double-slash in constructed URLs.
  const url = raw.endsWith("/") ? raw.slice(0, -1) : raw;

  if (process.env.NODE_ENV === "development") {
    console.log("[env] API base URL resolved to:", url);
  }

  return url;
};

export const env = {
  NEXT_PUBLIC_API_URL: getApiUrl(),
};
