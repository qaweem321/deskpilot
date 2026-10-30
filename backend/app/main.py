"""FastAPI app: wires settings, database, knowledge base, router and the agent graph together."""

import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.graph import AgentDeps, build_graph
from app.agent.llm import make_llm
from app.agent.router import KeywordRouter, LLMRouter, RemoteRouter, Router
from app.api import auth, chat, desk, voice
from app.config import Settings, get_settings
from app.db import Database
from app.deps import Services
from app.rag.store import Embedder, FastEmbedder, KnowledgeBase
from app.ratelimit import RateLimiter
from app.seed import seed

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
log = logging.getLogger("deskpilot")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def make_router(settings: Settings, llm) -> Router:  # noqa: ANN001
    if settings.router_mode == "remote":
        return RemoteRouter(settings.router_url or "")
    if settings.router_mode == "keywords":
        return KeywordRouter()
    return LLMRouter(llm)


def create_app(settings: Settings | None = None, embedder: Embedder | None = None, llm=None) -> FastAPI:  # noqa: ANN001
    """Build the app. Tests pass their own settings, a fake embedder and a scripted model."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN202
        db = Database(settings.database_url)
        db.create_all()
        if seed(db):
            log.info("Seeded the demo data")
        kb = KnowledgeBase.connect(settings.qdrant_url, embedder or FastEmbedder(settings.embed_model))
        log.info("Help center: %s passages", kb.ingest(KB_DIR))

        Path(settings.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(settings.checkpoint_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        model = llm or make_llm(settings)
        deps = AgentDeps(
            db=db,
            llm=model,
            router=make_router(settings, model),
            kb=kb,
            support_refund_limit=settings.support_refund_limit,
            kb_min_score=settings.kb_min_score,
        )
        voice_service = None
        if settings.voice_enabled:
            from app.voice import Voice

            voice_service = Voice(settings.whisper_model, settings.piper_voices_dir)
        app.state.services = Services(
            settings=settings,
            db=db,
            graph=build_graph(deps, checkpointer),
            login_limiter=RateLimiter(limit=10, window_seconds=60),
            chat_limiter=RateLimiter(limit=20, window_seconds=60),
            voice=voice_service,
        )
        try:
            yield
        finally:
            conn.close()
            db.engine.dispose()

    app = FastAPI(title="Deskpilot API", lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security(request: Request, call_next):  # noqa: ANN001, ANN202
        # CSRF: the session cookie is SameSite=Strict, and writes must also carry a custom header,
        # which a form on another site cannot add without a CORS preflight.
        if request.method in UNSAFE_METHODS and request.headers.get("x-requested-with") != "deskpilot":
            return JSONResponse({"detail": "Missing X-Requested-With header."}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    for module in (auth, desk, chat, voice):
        app.include_router(module.router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
