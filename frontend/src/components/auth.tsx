"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

const AuthContext = createContext<Me | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    api<Me>("/api/auth/me").then(setMe).catch(() => undefined); // 401 redirects to /login
  }, []);
  if (!me) {
    return (
      <main className="grid min-h-screen place-items-center">
        <p className="muted" role="status">
          Loading your desk...
        </p>
      </main>
    );
  }
  return <AuthContext.Provider value={me}>{children}</AuthContext.Provider>;
}

export function useMe(): Me {
  const me = useContext(AuthContext);
  if (!me) throw new Error("useMe must be used inside AuthProvider");
  return me;
}

export async function logout(): Promise<void> {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.replace("/");
  }
}
