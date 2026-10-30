"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { PasswordInput } from "@/components/password-input";
import { api } from "@/lib/api";
import { safeNext } from "@/lib/safe-next";

const DEMO = [
  ["viewer@deskpilot.test", "Viewer: read only"],
  ["support@deskpilot.test", "Support: refunds up to $50"],
  ["manager@deskpilot.test", "Manager: everything + audit log"],
];

export function LoginForm() {
  const next = safeNext(useSearchParams().get("next"));
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (sending) return;
    const form = new FormData(e.currentTarget);
    setSending(true);
    setError("");
    try {
      await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      window.location.replace(next); // full load: no stale signed-out pages in history
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
      setSending(false);
    }
  }

  function fill(email: string) {
    const emailInput = document.getElementById("email") as HTMLInputElement;
    const passwordInput = document.getElementById("password") as HTMLInputElement;
    emailInput.value = email;
    passwordInput.value = "deskpilot-demo";
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-1">
        <label htmlFor="email" className="text-sm font-medium">
          Email
        </label>
        <input id="email" name="email" type="email" className="input" autoComplete="username" required />
      </div>
      <div className="space-y-1">
        <label htmlFor="password" className="text-sm font-medium">
          Password
        </label>
        <PasswordInput id="password" name="password" />
      </div>
      {error ? (
        <p role="alert" className="text-sm" style={{ color: "var(--bad)" }}>
          {error}
        </p>
      ) : null}
      <button type="submit" className="btn btn-primary w-full" disabled={sending}>
        {sending ? "Signing in..." : "Sign in"}
      </button>
      <fieldset className="space-y-2 border-t pt-4" style={{ borderColor: "var(--border)" }}>
        <legend className="text-xs muted">Demo logins (fill the form)</legend>
        {DEMO.map(([email, label]) => (
          <button key={email} type="button" className="btn w-full justify-start text-xs" onClick={() => fill(email)}>
            {label}
          </button>
        ))}
      </fieldset>
    </form>
  );
}
