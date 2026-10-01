import Link from "next/link";
export default function NotFound() {
  return (
    <main className="status-page">
      <h1>Page not found</h1>
      <p>This page or resource is unavailable in your workspace.</p>
      <Link href="/overview">Return to Overview</Link>
    </main>
  );
}
