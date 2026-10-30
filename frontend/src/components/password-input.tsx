"use client";

import { useState } from "react";

export function PasswordInput({ id, name }: { id: string; name: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input id={id} name={name} type={visible ? "text" : "password"} className="input pr-16" autoComplete="current-password" required />
      <button
        type="button"
        className="absolute inset-y-0 right-2 my-auto h-fit text-xs font-semibold muted"
        aria-pressed={visible}
        onClick={() => setVisible((v) => !v)}
      >
        {visible ? "Hide" : "Show"} <span className="sr-only">password</span>
      </button>
    </div>
  );
}
