"use client";

import { useEffect, useRef, useState } from "react";
import { api, rawApi } from "@/lib/api";

type VoiceInfo = { enabled: boolean; speak_languages: string[] };
let infoPromise: Promise<VoiceInfo> | null = null;

/** Asked once per page load: is voice on, and which languages can be spoken? */
export function useVoiceInfo(): VoiceInfo {
  const [info, setInfo] = useState<VoiceInfo>({ enabled: false, speak_languages: [] });
  useEffect(() => {
    infoPromise ??= api<VoiceInfo>("/api/voice").catch(() => ({ enabled: false, speak_languages: [] }));
    infoPromise.then(setInfo);
  }, []);
  return info;
}

/** Record from the microphone, send it to Whisper, hand back the text. */
export function MicButton({ onText, disabled }: { onText: (text: string) => void; disabled: boolean }) {
  const [state, setState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);

  async function start() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("transcribing");
        try {
          const form = new FormData();
          form.append("audio", new Blob(chunks, { type: rec.mimeType }), "speech.webm");
          const response = await rawApi("/api/voice/transcribe", { method: "POST", body: form });
          const { text } = (await response.json()) as { text: string };
          if (text) onText(text);
          else setError("I didn't catch that.");
        } catch (e) {
          setError(e instanceof Error ? e.message : "Transcription failed.");
        } finally {
          setState("idle");
        }
      };
      recorder.current = rec;
      rec.start();
      setState("recording");
    } catch {
      setError("Microphone not available.");
    }
  }

  const label = state === "recording" ? "Stop recording" : state === "transcribing" ? "Transcribing..." : "Speak";
  return (
    <>
      <button
        type="button"
        className="btn"
        aria-label={label}
        title={label}
        disabled={disabled || state === "transcribing"}
        onClick={() => (state === "recording" ? recorder.current?.stop() : void start())}
        style={state === "recording" ? { borderColor: "var(--bad)", color: "var(--bad)" } : undefined}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
        </svg>
        {state === "recording" ? <span className="text-xs">Stop</span> : null}
      </button>
      {error ? (
        <span role="status" className="text-xs" style={{ color: "var(--bad)" }}>
          {error}
        </span>
      ) : null}
    </>
  );
}

/** Guess the language from the script: enough to pick a Piper voice. */
export function guessLanguage(text: string): string {
  if (/[؀-ۿ]/.test(text)) return /[ٹڈڑںھہے]/.test(text) ? "ur" : "ar";
  if (/[ऀ-ॿ]/.test(text)) return "hi";
  return "en";
}

export function SpeakButton({ text, languages }: { text: string; languages: string[] }) {
  const [busy, setBusy] = useState(false);
  const language = guessLanguage(text);
  if (!languages.includes(language)) return null;

  async function play() {
    setBusy(true);
    try {
      const clean = text.replace(/\[\d+\]/g, "").slice(0, 1500);
      const response = await rawApi("/api/voice/speak", { method: "POST", body: JSON.stringify({ text: clean, language }) });
      const url = URL.createObjectURL(await response.blob());
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button type="button" className="text-xs underline muted" onClick={() => void play()} disabled={busy}>
      {busy ? "Loading audio..." : "Read aloud"}
    </button>
  );
}
