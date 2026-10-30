"use client";

import { useCallback, useEffect, useState } from "react";
import { api, rawApi } from "@/lib/api";
import { readEvents, type ChatEvent, type PendingAction, type Source } from "@/lib/sse";

export type Step = { kind: "route" | "tool"; label: string; outcome?: string };
export type ChatMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; steps: Step[]; sources: Source[]; error?: boolean };

const THREAD_KEY = "deskpilot-thread";
const OUTCOME_LABEL: Record<string, string> = {
  done: "done",
  denied: "not allowed",
  rejected: "refused by a business rule",
  invalid: "invalid input",
  not_found: "not found",
  cancelled: "declined",
};

function storedThread(userId: number): string | null {
  try {
    const value = sessionStorage.getItem(`${THREAD_KEY}-${userId}`);
    return value && value.startsWith(`u${userId}-`) ? value : null;
  } catch {
    return null;
  }
}

function storeThread(userId: number, threadId: string | null): void {
  try {
    if (threadId) sessionStorage.setItem(`${THREAD_KEY}-${userId}`, threadId);
    else sessionStorage.removeItem(`${THREAD_KEY}-${userId}`);
  } catch {
    /* storage blocked: the conversation just won't survive a reload */
  }
}

/** All chat state and server calls, kept out of the UI so it can be tested on its own. */
export function useChat(userId: number, onActionDone: () => void) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [busy, setBusy] = useState(false);

  // Restore the open conversation (and any confirmation still waiting) after a reload.
  useEffect(() => {
    const saved = storedThread(userId);
    if (!saved) return;
    api<{ messages: { role: "user" | "assistant"; text: string }[]; pending: PendingAction[] }>(
      `/api/chat/${encodeURIComponent(saved)}`,
    )
      .then((h) => {
        setThreadId(saved);
        setMessages(
          h.messages.map((m): ChatMessage =>
            m.role === "user" ? { role: "user", text: m.text } : { role: "assistant", text: m.text, steps: [], sources: [] },
          ),
        );
        setPending(h.pending);
      })
      .catch(() => storeThread(userId, null));
  }, [userId]);

  const stream = useCallback(
    async (path: string, body: object) => {
      setBusy(true);
      let current: Extract<ChatMessage, { role: "assistant" }> = { role: "assistant", text: "", steps: [], sources: [] };
      setMessages((m) => [...m, current]);
      const update = (patch: Partial<typeof current>) => {
        current = { ...current, ...patch };
        const snapshot = current;
        setMessages((m) => [...m.slice(0, -1), snapshot]);
      };
      let wrote = false;
      const handle = (event: ChatEvent) => {
        switch (event.type) {
          case "thread":
            setThreadId(event.thread_id);
            storeThread(userId, event.thread_id);
            break;
          case "route":
            update({ steps: [...current.steps, { kind: "route", label: `Routed to ${event.route}` }] });
            break;
          case "tool_call":
            update({ steps: [...current.steps, { kind: "tool", label: event.name }] });
            break;
          case "tool_result": {
            const steps = [...current.steps];
            const index = steps.findLastIndex((s) => s.kind === "tool" && s.label === event.name && !s.outcome);
            const outcome = OUTCOME_LABEL[event.outcome] ?? event.outcome;
            // After a confirmation the result arrives in a new reply, so the step may not be here yet.
            if (index >= 0) steps[index] = { ...steps[index], outcome };
            else steps.push({ kind: "tool", label: event.name, outcome });
            if (event.outcome === "done") wrote = true;
            update({ steps });
            break;
          }
          case "confirm":
            setPending(event.actions);
            update({
              text: "This needs your confirmation before I do it.",
              steps: current.steps.map((s) => (s.kind === "tool" && !s.outcome ? { ...s, outcome: "waiting for you" } : s)),
            });
            break;
          case "answer":
            update({ text: event.text, sources: event.sources });
            break;
          case "error":
            update({ text: event.message, error: true });
            break;
        }
      };
      try {
        const response = await rawApi(path, { method: "POST", body: JSON.stringify(body) });
        await readEvents(response, handle);
      } catch (e) {
        handle({ type: "error", message: e instanceof Error ? e.message : "Something went wrong." });
      } finally {
        setBusy(false);
        if (wrote) onActionDone();
      }
    },
    [userId, onActionDone],
  );

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy || pending.length) return;
      setMessages((m) => [...m, { role: "user", text: message }]);
      await stream("/api/chat", { message, thread_id: threadId });
    },
    [busy, pending.length, stream, threadId],
  );

  const decide = useCallback(
    async (approve: boolean) => {
      if (!threadId || !pending.length || busy) return;
      const decisions = Object.fromEntries(pending.map((a) => [a.id, approve]));
      setPending([]);
      setMessages((m) => [...m, { role: "user", text: approve ? "Yes, do it." : "No, don't do it." }]);
      await stream("/api/chat/confirm", { thread_id: threadId, decisions });
    },
    [busy, pending, stream, threadId],
  );

  const reset = useCallback(() => {
    storeThread(userId, null);
    setThreadId(null);
    setMessages([]);
    setPending([]);
  }, [userId]);

  return { messages, pending, busy, send, decide, reset };
}
