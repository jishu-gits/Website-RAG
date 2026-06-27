/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // BUG 3 FIX: The rewrites() block was removed.
  //
  // Previously: source "/api/:path*" → destination "${NEXT_PUBLIC_API_URL}/api/:path*"
  // That rewrite was never active on Vercel (vercel.json doesn't exist) and created
  // a double "/api" path if NEXT_PUBLIC_API_URL already contained "/api".
  //
  // The frontend now calls the Render backend DIRECTLY via NEXT_PUBLIC_API_URL.
  // api.ts constructs:  `${NEXT_PUBLIC_API_URL}/chat`
  // which resolves to:  https://website-rag-qxbv.onrender.com/api/chat   ✓
  //
  // NEXT_PUBLIC_API_URL must be set in Vercel environment variables:
  //   Key:   NEXT_PUBLIC_API_URL
  //   Value: https://website-rag-qxbv.onrender.com/api
  //   (include /api, no trailing slash)
};

module.exports = nextConfig;