"use client";

import { useEffect, useRef, useState } from "react";
import type { PendingAction } from "@/lib/sse";
import { useChat, type ChatMessage } from "./use-chat";
import { MicButton, SpeakButton, useVoiceInfo } from "./voice";

const EXAMPLES = ["Where is ORD-1004?", "How long do refunds take?", "Refund $20 on ORD-1002, the seam is torn"];

export function ChatPanel({ userId, onActionDone }: { userId: number; onActionDone: () => void }) {
  const { messages, pending, busy, send, decide, reset } = useChat(userId, onActionDone);
  const [draft, setDraft] = useState("");
  const voice = useVoiceInfo();
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, which React rejects.
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages, pending]);

  function submit(text: string) {
    setDraft("");
    void send(text);
  }

  return (
    <section className="panel flex h-full min-h-[28rem] flex-col" aria-label="Assistant">
      <header className="flex items-center justify-between border-b p-3" style={{ borderColor: "var(--border)" }}>
        <div>
          <h2 className="font-semibold">Deskpilot assistant</h2>
          <p className="text-xs muted">Acts with your permissions. Changes to orders ask you first.</p>
        </div>
        <button type="button" className="btn whitespace-nowrap text-xs" onClick={reset} disabled={busy}>
          New chat
        </button>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
        {messages.length === 0 ? (
          <div className="space-y-2 text-sm muted">
            <p>Ask about an order, a ticket or a store policy. In English or another language.</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((e) => (
                <button key={e} type="button" className="chip" onClick={() => submit(e)} disabled={busy}>
                  {e}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {messages.map((m, i) => (
          <Message key={i} message={m} speakLanguages={voice.speak_languages} />
        ))}
        {busy ? <p className="text-xs muted">Working... (a local model on a CPU can take 20-40 seconds)</p> : null}
        {pending.length ? <ConfirmCard actions={pending} onDecide={(ok) => void decide(ok)} disabled={busy} /> : null}
        <div ref={bottom} />
      </div>

      <form
        className="flex items-center gap-2 border-t p-3"
        style={{ borderColor: "var(--border)" }}
        onSubmit={(e) => {
          e.preventDefault();
          submit(draft);
        }}
      >
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <input
          id="chat-input"
          className="input"
          value={draft}
          maxLength={2000}
          placeholder={pending.length ? "Confirm or decline above first" : "Ask Deskpilot..."}
          onChange={(e) => setDraft(e.target.value)}
          disabled={busy || pending.length > 0}
          dir="auto"
        />
        {voice.enabled ? <MicButton onText={submit} disabled={busy || pending.length > 0} /> : null}
        <button type="submit" className="btn btn-primary" disabled={busy || !draft.trim() || pending.length > 0}>
          {busy ? "Sending..." : "Send"}
        </button>
      </form>
    </section>
  );
}

function Message({ message, speakLanguages }: { message: ChatMessage; speakLanguages: string[] }) {
  if (message.role === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-xl px-3 py-2 text-sm" style={{ background: "var(--accent)", color: "var(--accent-text)" }} dir="auto">
        {message.text}
      </div>
    );
  }
  return (
    <div className="max-w-[92%] space-y-1">
      {message.steps.length ? (
        <ol className="flex flex-wrap gap-1" aria-label="Steps">
          {message.steps.map((s, i) => (
            <li key={i} className="chip" style={s.outcome && s.outcome !== "done" && s.outcome !== "waiting for you" ? { color: "var(--warn)" } : undefined}>
              {s.kind === "tool" ? "Tool: " : ""}
              {s.label}
              {s.outcome ? ` · ${s.outcome}` : s.kind === "tool" ? " · ..." : ""}
            </li>
          ))}
        </ol>
      ) : null}
      {message.text ? (
        <div
          className="whitespace-pre-wrap rounded-xl px-3 py-2 text-sm"
          style={{ background: "var(--chip)", color: message.error ? "var(--bad)" : undefined }}
          dir="auto"
        >
          {message.text}
        </div>
      ) : null}
      {message.sources.length ? (
        <p className="text-xs muted">
          Sources: {message.sources.map((s) => `[${s.n}] ${s.heading}`).join(" · ")}
        </p>
      ) : null}
      {message.text && !message.error ? <SpeakButton text={message.text} languages={speakLanguages} /> : null}
    </div>
  );
}

export function ConfirmCard({
  actions,
  onDecide,
  disabled,
}: {
  actions: PendingAction[];
  onDecide: (approve: boolean) => void;
  disabled: boolean;
}) {
  return (
    <div role="alertdialog" aria-labelledby="confirm-title" className="rounded-xl border p-3" style={{ borderColor: "var(--warn)" }}>
      <p id="confirm-title" className="font-semibold">
        Are you sure?
      </p>
      <ul className="my-2 list-disc pl-5 text-sm">
        {actions.map((a) => (
          <li key={a.id}>{a.summary}</li>
        ))}
      </ul>
      <div className="flex gap-2">
        <button type="button" className="btn btn-danger" onClick={() => onDecide(true)} disabled={disabled}>
          Yes, do it
        </button>
        <button type="button" className="btn" onClick={() => onDecide(false)} disabled={disabled}>
          No, cancel
        </button>
      </div>
    </div>
  );
}
