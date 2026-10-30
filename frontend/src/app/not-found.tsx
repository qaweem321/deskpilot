import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center px-4 text-center">
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Page not found</h1>
        <p className="muted">This page doesn&apos;t exist.</p>
        <Link href="/" className="btn btn-primary">
          Back to the start
        </Link>
      </div>
    </main>
  );
}
