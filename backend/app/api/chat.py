"""Chat with the assistant over Server-Sent Events, so the UI can show each step as it happens."""

import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.agent.graph import new_thread_id, owns_thread
from app.agent.guardrails import redact
from app.deps import ServicesDep, UserDep
from app.security import Principal

router = APIRouter(prefix="/api/chat", tags=["chat"])
log = logging.getLogger(__name__)
SPECIALISTS = {"orders_agent", "tickets_agent"}


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, max_length=80)


class ConfirmBody(BaseModel):
    thread_id: str = Field(max_length=80)
    decisions: dict[str, bool]


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def graph_config(user: Principal, thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "principal": user}}


def stream_run(graph: Any, payload: Any, config: dict) -> Iterator[str]:
    """Translate LangGraph updates into small UI events. Always ends with "done" or "error"."""
    thread_id = config["configurable"]["thread_id"]
    yield sse({"type": "thread", "thread_id": thread_id})
    try:
        for update in graph.stream(payload, config, stream_mode="updates"):
            for node, data in update.items():
                if node == "__interrupt__":
                    for item in data:
                        yield sse({"type": "confirm", "actions": item.value["actions"]})
                elif node == "route" and data:
                    yield sse({"type": "route", "route": data["route"]})
                elif node in SPECIALISTS and data:
                    for message in data.get("messages", []):
                        for call in getattr(message, "tool_calls", []) or []:
                            yield sse({"type": "tool_call", "name": call["name"], "args": call["args"]})
                elif node == "tools" and data:
                    for message in data.get("messages", []):
                        outcome = (message.artifact or {}).get("outcome", "cancelled")
                        yield sse({"type": "tool_result", "name": message.name, "outcome": outcome})

        state = graph.get_state(config)
        if state.interrupts:
            yield sse({"type": "waiting"})
        else:
            values = state.values
            last = values["messages"][-1]
            yield sse(
                {
                    "type": "answer",
                    "text": str(last.content),
                    "route": values.get("route", ""),
                    "sources": values.get("sources", []),
                }
            )
        yield sse({"type": "done"})
    except Exception as exc:
        log.exception("Assistant run failed for thread %s", thread_id)
        message = "The assistant could not finish. Is the language model running?"
        if "timed out" in str(exc).lower() or "timeout" in type(exc).__name__.lower():
            message = "The language model took too long to answer. Try again in a moment."
        yield sse({"type": "error", "message": message})


def streaming(events: Iterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("")
def chat(body: ChatBody, svc: ServicesDep, user: UserDep) -> StreamingResponse:
    if not svc.chat_limiter.allow(f"user:{user.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Slow down a little: too many messages.")
    thread_id = body.thread_id or new_thread_id(user.id)
    if not owns_thread(user.id, thread_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    config = graph_config(user, thread_id)
    if svc.graph.get_state(config).interrupts:
        raise HTTPException(status.HTTP_409_CONFLICT, "Answer the pending confirmation first.")
    log.info("chat user=%s thread=%s text=%s", user.id, thread_id, redact(body.message[:200]))
    return streaming(stream_run(svc.graph, {"messages": [HumanMessage(body.message)]}, config))


@router.post("/confirm")
def confirm(body: ConfirmBody, svc: ServicesDep, user: UserDep) -> StreamingResponse:
    if not owns_thread(user.id, body.thread_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    config = graph_config(user, body.thread_id)
    if not svc.graph.get_state(config).interrupts:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for confirmation.")
    return streaming(stream_run(svc.graph, Command(resume=body.decisions), config))


@router.get("/{thread_id}")
def history(thread_id: str, svc: ServicesDep, user: UserDep) -> dict:
    if not owns_thread(user.id, thread_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    state = svc.graph.get_state(graph_config(user, thread_id))
    messages = []
    for m in state.values.get("messages", []) if state.values else []:
        if isinstance(m, HumanMessage):
            messages.append({"role": "user", "text": str(m.content)})
        elif isinstance(m, AIMessage) and m.content and not m.tool_calls:
            messages.append({"role": "assistant", "text": str(m.content)})
        elif isinstance(m, ToolMessage):
            continue
    pending = [i.value["actions"] for i in state.interrupts] if state.values else []
    return {"thread_id": thread_id, "messages": messages, "pending": pending[0] if pending else []}
