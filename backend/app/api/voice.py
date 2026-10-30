from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.deps import ServicesDep, UserDep

router = APIRouter(prefix="/api/voice", tags=["voice"])
MAX_AUDIO_BYTES = 5 * 1024 * 1024


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}$")


def _voice(svc: ServicesDep):  # noqa: ANN202
    if svc.voice is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Voice is turned off on this server.")
    return svc.voice


@router.get("")
def voice_info(svc: ServicesDep, _: UserDep) -> dict:
    if svc.voice is None:
        return {"enabled": False, "speak_languages": []}
    return {"enabled": True, "speak_languages": sorted(svc.voice.voices())}


@router.post("/transcribe")
async def transcribe(audio: UploadFile, svc: ServicesDep, _: UserDep) -> dict:
    voice = _voice(svc)
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Recordings can be up to 5 MB.")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The recording is empty.")
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(voice.transcribe, data)


@router.post("/speak")
def speak(body: SpeakBody, svc: ServicesDep, _: UserDep) -> Response:
    audio = _voice(svc).speak(body.text, body.language)
    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No voice installed for '{body.language}'.")
    return Response(audio, media_type="audio/wav")
