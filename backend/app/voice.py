"""Speech in and out, fully local: faster-whisper (speech-to-text, ~100 languages) and Piper
(text-to-speech). Optional: install with `uv sync --extra voice` and set VOICE_ENABLED=true."""

import io
import tempfile
import threading
import wave
from pathlib import Path


class Voice:
    def __init__(self, whisper_model: str, voices_dir: str) -> None:
        self.whisper_model = whisper_model
        self.voices_dir = Path(voices_dir)
        self._stt = None
        self._tts: dict[str, object] = {}
        self._lock = threading.Lock()

    def _whisper(self):  # noqa: ANN202
        with self._lock:
            if self._stt is None:
                from faster_whisper import WhisperModel

                self._stt = WhisperModel(self.whisper_model, device="cpu", compute_type="int8")
            return self._stt

    def transcribe(self, audio: bytes) -> dict:
        with tempfile.NamedTemporaryFile(suffix=".audio") as f:
            f.write(audio)
            f.flush()
            segments, info = self._whisper().transcribe(f.name, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "language": info.language}

    def voices(self) -> dict[str, Path]:
        """Installed Piper voices by language code, e.g. {"en": .../en_US-lessac-medium.onnx}."""
        found: dict[str, Path] = {}
        for model in sorted(self.voices_dir.glob("*.onnx")):
            found.setdefault(model.name.split("_")[0], model)
        return found

    def speak(self, text: str, language: str) -> bytes | None:
        model = self.voices().get(language)
        if model is None:
            return None
        with self._lock:
            if language not in self._tts:
                from piper import PiperVoice

                self._tts[language] = PiperVoice.load(str(model))
            voice = self._tts[language]
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            voice.synthesize_wav(text, wav)  # type: ignore[attr-defined]
        return buffer.getvalue()
