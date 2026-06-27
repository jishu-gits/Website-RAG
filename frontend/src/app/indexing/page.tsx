import IndexWebsiteClient from "./IndexWebsiteClient";

export const dynamic = "force-dynamic";

export default function Page() {
  // Busting Vercel Next.js cache
  return <IndexWebsiteClient />;
}
