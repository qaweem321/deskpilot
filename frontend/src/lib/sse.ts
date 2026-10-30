export type ChatEvent =
  | { type: "thread"; thread_id: string }
  | { type: "route"; route: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; outcome: string }
  | { type: "confirm"; actions: PendingAction[] }
  | { type: "waiting" }
  | { type: "answer"; text: string; route: string; sources: Source[] }
  | { type: "error"; message: string }
  | { type: "done" };

export type PendingAction = { id: string; action: string; summary: string };
export type Source = { n: number; doc: string; heading: string; score: number };

/**
 * Read a Server-Sent Events stream of JSON events. A stream that stops before "done" or "error"
 * is reported as an error, so an answer is never silently dropped.
 */
export async function readEvents(response: Response, onEvent: (event: ChatEvent) => void): Promise<void> {
  if (!response.body) throw new Error("The server sent no data.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const event = JSON.parse(line.slice(6)) as ChatEvent;
        if (event.type === "done" || event.type === "error") finished = true;
        onEvent(event);
      }
    }
  }
  if (!finished) onEvent({ type: "error", message: "The connection closed before the answer finished." });
}
