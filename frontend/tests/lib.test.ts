import { formatDate, formatDateTime } from "@/lib/format";
import { loginUrl, safeNext } from "@/lib/safe-next";
import { readEvents, type ChatEvent } from "@/lib/sse";
import { guessLanguage } from "@/components/voice";

describe("safeNext", () => {
  it("keeps same-site paths", () => {
    expect(safeNext("/app/audit?x=1")).toBe("/app/audit?x=1");
  });
  it.each(["//evil.com", "/\\evil.com", "https://evil.com", "javascript:alert(1)", "", null, "/login"])(
    "rejects %s",
    (value) => expect(safeNext(value)).toBe("/app"),
  );
  it("builds the login URL", () => {
    expect(loginUrl("/app/audit")).toBe("/login?next=%2Fapp%2Faudit");
  });
});

describe("dates", () => {
  it("formats in UTC without ambiguity", () => {
    expect(formatDate("2026-10-11T23:30:00Z")).toBe("Oct 11, 2026");
    expect(formatDateTime("2026-10-11T07:05:00Z")).toBe("Oct 11, 2026, 07:05 UTC");
    expect(formatDate("nonsense")).toBe("");
  });
});

function streamOf(...chunks: string[]): Response {
  const body = new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(new TextEncoder().encode(c)));
      controller.close();
    },
  });
  return new Response(body);
}

describe("readEvents", () => {
  it("parses events split across chunks", async () => {
    const seen: ChatEvent[] = [];
    await readEvents(streamOf('data: {"type":"route","rou', 'te":"orders"}\n\ndata: {"type":"done"}\n\n'), (e) => seen.push(e));
    expect(seen.map((e) => e.type)).toEqual(["route", "done"]);
  });
  it("reports a stream that ends without done", async () => {
    const seen: ChatEvent[] = [];
    await readEvents(streamOf('data: {"type":"route","route":"orders"}\n\n'), (e) => seen.push(e));
    expect(seen.at(-1)).toEqual({ type: "error", message: expect.stringContaining("closed") });
  });
});

describe("guessLanguage", () => {
  it("detects scripts", () => {
    expect(guessLanguage("Where is my order?")).toBe("en");
    expect(guessLanguage("ریفنڈ میں کتنا وقت لگتا ہے؟")).toBe("ur");
    expect(guessLanguage("أين طلبي؟")).toBe("ar");
  });
});
