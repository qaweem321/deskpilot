"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { logout, useMe } from "./auth";
import { Logo } from "./logo";

export function AppHeader() {
  const me = useMe();
  const path = usePathname();
  const [leaving, setLeaving] = useState(false);
  const links = [
    { href: "/app", label: "Dashboard" },
    ...(me.permissions.includes("audit.read") ? [{ href: "/app/audit", label: "Audit log" }] : []),
    { href: "/app/settings", label: "Settings" },
  ];
  return (
    <header className="border-b" style={{ borderColor: "var(--border)", background: "var(--panel)" }}>
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Logo href="/app" />
        <nav aria-label="Main" className="flex gap-4 text-sm">
          {links.map((l) => (
            <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined} className={path === l.href ? "font-semibold" : "muted"}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span>
            {me.name} <span className="chip">{me.role}</span>
          </span>
          <button
            type="button"
            className="btn text-xs"
            disabled={leaving}
            onClick={() => {
              setLeaving(true);
              void logout();
            }}
          >
            {leaving ? "Signing out..." : "Sign out"}
          </button>
        </div>
      </div>
    </header>
  );
}
