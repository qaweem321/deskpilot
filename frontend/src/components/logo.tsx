import Link from "next/link";

export function Logo({ href }: { href: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 font-bold">
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <rect width="24" height="24" rx="6" fill="var(--accent)" />
        <path d="M6 12h8m-3-4 4 4-4 4" stroke="var(--accent-text)" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="17.5" cy="12" r="1.5" fill="var(--accent-text)" />
      </svg>
      Deskpilot
    </Link>
  );
}
