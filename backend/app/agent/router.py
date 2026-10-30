"""Supervisor step: decide which specialist agent handles the request.

Three interchangeable backends: the chat model (default), the fine-tuned router service from the
routelab project (ROUTER_MODE=remote), or plain keywords (tests and offline use). Whatever the
backend, the result is one of ROUTES, and keywords are the fallback when a backend fails.
"""

import logging
import re
from typing import Literal, Protocol

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

Route = Literal["orders", "tickets", "knowledge", "other"]
ROUTES: tuple[Route, ...] = ("orders", "tickets", "knowledge", "other")
log = logging.getLogger(__name__)


class Router(Protocol):
    def route(self, text: str) -> Route: ...


_ORDER_ID = re.compile(r"\bORD-\d+", re.I)
_TICKET_ID = re.compile(r"\bTCK-\d+", re.I)
_TICKET_WORDS = re.compile(r"\b(ticket|tickets|complaint|case)\b", re.I)
_ORDER_WORDS = re.compile(r"\b(cancel|refund|order|orders|parcel|package|purchase)\b", re.I)
_POLICY_WORDS = re.compile(
    r"\b(policy|policies|how long|how many days|warranty|guarantee|shipping|delivery time|"
    r"return window|can (i|we|customers)|do (you|we)|opening hours|payment methods?)\b",
    re.I,
)
_SMALLTALK = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|who are you|what can you do)\b", re.I)


class KeywordRouter:
    def route(self, text: str) -> Route:
        if _SMALLTALK.search(text) and len(text) < 60:
            return "other"
        if _TICKET_ID.search(text) or _TICKET_WORDS.search(text):
            return "tickets"
        if _ORDER_ID.search(text):
            return "orders"
        if _POLICY_WORDS.search(text):
            return "knowledge"
        if _ORDER_WORDS.search(text):
            return "orders"
        return "knowledge"


ROUTER_PROMPT = """You route requests from support staff at an online outdoor-gear store.
Answer with exactly one word:
orders - look up, search, cancel or refund a specific order or a customer's orders
tickets - read, find, open, close or change support tickets
knowledge - questions about store policy: returns, refunds rules, shipping, warranty, payments
other - greetings, thanks, or anything unrelated to the store

Examples:
"Refund $20 on ORD-1003, strap missing" -> orders
"How many days do customers have to return an item?" -> knowledge
"Close TCK-2002" -> tickets
"Open a ticket for omar@example.com about a late parcel" -> tickets
"Write me a poem" -> other"""


def parse_route(text: str) -> Route | None:
    word = re.search(r"orders|tickets|knowledge|other", text.lower())
    return word.group(0) if word else None  # type: ignore[return-value]


class LLMRouter:
    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm.bind(max_tokens=4)
        self.fallback = KeywordRouter()

    def route(self, text: str) -> Route:
        try:
            reply = self.llm.invoke([SystemMessage(ROUTER_PROMPT), HumanMessage(text[:1000])])
            route = parse_route(str(reply.content))
        except Exception:  # model down or timed out: keep working with keywords
            log.warning("LLM router failed; using keywords", exc_info=True)
            route = None
        return route or self.fallback.route(text)


class RemoteRouter:
    """Calls the fine-tuned routing model served by routelab: POST {text} -> {route}."""

    def __init__(self, url: str, timeout: float = 20) -> None:
        self.url = url
        self.client = httpx.Client(timeout=timeout)
        self.fallback = KeywordRouter()

    def route(self, text: str) -> Route:
        try:
            response = self.client.post(f"{self.url}/route", json={"text": text[:1000]})
            response.raise_for_status()
            route = response.json().get("route")
            if route in ROUTES:
                return route
        except (httpx.HTTPError, ValueError):
            log.warning("Remote router failed; using keywords", exc_info=True)
        return self.fallback.route(text)
