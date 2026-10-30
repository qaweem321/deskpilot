const FALLBACK = "/app";

/** Only same-site paths are allowed as a post-login target ("/app/audit", never "//evil.com"). */
export function safeNext(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return FALLBACK;
  try {
    const url = new URL(value, "http://local.invalid");
    if (url.origin !== "http://local.invalid") return FALLBACK;
    if (url.pathname === "/login") return FALLBACK;
    return url.pathname + url.search + url.hash;
  } catch {
    return FALLBACK;
  }
}

export function loginUrl(currentPath: string): string {
  return `/login?next=${encodeURIComponent(safeNext(currentPath))}`;
}
