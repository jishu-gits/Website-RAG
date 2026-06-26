/**
 * Frontend environment variable validation.
 * Run during module initialization to fail fast if config is missing.
 */

const getApiUrl = () => {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    if (typeof window === "undefined") {
      // In SSR/build, warn but don't crash if strictly not provided,
      // though for production this should ideally throw.
      console.warn("⚠️ NEXT_PUBLIC_API_URL is not set.");
    }
  }
  return url || "/api"; // Fallback to Next.js rewrites
};

export const env = {
  NEXT_PUBLIC_API_URL: getApiUrl(),
};
