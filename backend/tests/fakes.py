"""A scripted chat model: returns prepared replies in order and records what it was shown."""

from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

Reply = AIMessage | str | Callable[[list[BaseMessage]], AIMessage | str]


class ScriptedLLM(BaseChatModel):
    _replies: list[Reply] = PrivateAttr(default_factory=list)
    _calls: list[dict] = PrivateAttr(default_factory=list)
    _bound_tools: list[str] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def script(self, *replies: Reply) -> "ScriptedLLM":
        self._replies.extend(replies)
        return self

    @property
    def calls(self) -> list[dict]:
        return self._calls

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedLLM":  # type: ignore[override]
        self._bound_tools = [t["function"]["name"] for t in tools]
        return self

    def bind(self, **kwargs: Any) -> "ScriptedLLM":  # type: ignore[override]
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        self._calls.append({"messages": messages, "tools": list(self._bound_tools)})
        self._bound_tools = []
        if not self._replies:
            raise AssertionError("ScriptedLLM ran out of replies")
        reply = self._replies.pop(0)
        if callable(reply):
            reply = reply(messages)
        message = reply if isinstance(reply, AIMessage) else AIMessage(reply)
        return ChatResult(generations=[ChatGeneration(message=message)])


def call(name: str, call_id: str = "call_1", **args: Any) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])
