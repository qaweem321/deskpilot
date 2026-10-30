import { loginUrl } from "./safe-next";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Fetch the backend (proxied under /api). Sends the CSRF header; a 401 means the session ended. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await rawApi(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function rawApi(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", "deskpilot");
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (response.status === 401 && !path.startsWith("/api/auth/login")) {
    window.location.replace(loginUrl(window.location.pathname + window.location.search));
    throw new ApiError(401, "Your session ended. Please sign in again.");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, message);
  }
  return response;
}
