"""The multi-agent graph (LangGraph).

    guard_input -> route -> orders_agent  <-> confirm -> tools   -> guard_output
                         -> tickets_agent <-> confirm -> tools   -> guard_output
                         -> knowledge (RAG over the help center, cited)
                         -> other (fixed reply, no model call)

Security model: the assistant acts with the signed-in user's own permissions. Tools the user
may not use are never shown to the model, every call is checked again when it runs, destructive
calls pause the graph (interrupt) until the human approves, and everything is audited.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import ValidationError

from app.agent import prompts
from app.agent.guardrails import (
    best_supporting_passage,
    check_grounding,
    cited_sources,
    looks_like_injection,
    wrap_tool_output,
)
from app.agent.router import Router
from app.db import Database
from app.rag.store import KnowledgeBase
from app.security import Principal
from app.services import actions
from app.services.formatting import day

MAX_TOOL_ROUNDS = 4
HISTORY_TURNS = 3
MAX_REPLY_TOKENS = 220  # earlier user turns the specialists still see


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    route: str
    turn_start: int
    rounds: int
    approvals: dict[str, bool]
    sources: list[dict]
    blocked: bool


@dataclass
class AgentDeps:
    db: Database
    llm: BaseChatModel
    router: Router
    kb: KnowledgeBase | None
    support_refund_limit: Decimal
    kb_min_score: float = 0.45


def principal_of(config: RunnableConfig) -> Principal:
    principal = config.get("configurable", {}).get("principal")
    if not isinstance(principal, Principal):
        raise RuntimeError("The graph must be run with the signed-in principal in its config.")
    return principal


def tool_schema(action: actions.Action) -> dict:
    """OpenAI tool format, simplified for small models (no titles, optional = not required)."""
    schema = action.args_model.model_json_schema()
    props = {}
    for name, prop in schema.get("properties", {}).items():
        prop = dict(prop)
        if "anyOf" in prop:  # Optional[X] -> X
            prop.update(next(p for p in prop.pop("anyOf") if p.get("type") != "null"))
        prop.pop("title", None)
        prop.pop("default", None)
        props[name] = prop
    return {
        "type": "function",
        "function": {
            "name": action.name,
            "description": action.description,
            "parameters": {"type": "object", "properties": props, "required": schema.get("required", [])},
        },
    }


def last_human(state: State) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def recent_history(messages: list[AnyMessage]) -> list[AnyMessage]:
    """The last few turns, cut at a user message so tool calls and results stay paired."""
    human_idx = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    start = human_idx[-HISTORY_TURNS] if len(human_idx) >= HISTORY_TURNS else 0
    return messages[start:]


def this_turn(state: State) -> list[AnyMessage]:
    return state["messages"][state.get("turn_start", 0) :]


def build_graph(deps: AgentDeps, checkpointer: Any = None):  # noqa: C901, ANN201  (one graph, read top to bottom)
    ctx = actions.ActionContext(support_refund_limit=deps.support_refund_limit)

    def guard_input(state: State) -> State:
        reset: State = {
            "turn_start": len(state["messages"]) - 1,
            "rounds": 0,
            "approvals": {},
            "sources": [],
            "blocked": False,
            "route": "",
        }
        text = last_human(state)
        if looks_like_injection(text):
            reset["blocked"] = True
            reset["messages"] = [
                AIMessage(
                    "That message looks like an attempt to change my instructions, so I won't act "
                    "on it. Ask me about an order, a ticket or a store policy instead."
                )
            ]
        return reset

    def route(state: State) -> State:
        return {"route": deps.router.route(last_human(state))}

    def make_specialist(group: str):  # noqa: ANN202
        def specialist(state: State, config: RunnableConfig) -> State:
            principal = principal_of(config)
            allowed = actions.actions_for(principal, group)
            system = SystemMessage(
                prompts.SPECIALIST.format(
                    name=principal.name,
                    role=principal.role.value,
                    group=group,
                    allowed=", ".join(a.name.replace("_", " ") for a in allowed) or "nothing in this area",
                    today=day(datetime.now(UTC)),
                )
            )
            rounds = state.get("rounds", 0) + 1
            # Short replies: on a CPU-only model every generated token costs ~0.2 s.
            llm = deps.llm.bind(max_tokens=MAX_REPLY_TOKENS)
            if allowed and rounds <= MAX_TOOL_ROUNDS:
                llm = deps.llm.bind_tools(  # type: ignore[assignment]
                    [tool_schema(a) for a in allowed], max_tokens=MAX_REPLY_TOKENS
                )
            reply = llm.invoke([system, *recent_history(state["messages"])])
            if not isinstance(reply, AIMessage):
                reply = AIMessage(str(reply.content))
            return {"messages": [reply], "rounds": rounds}

        return specialist

    def confirm(state: State, config: RunnableConfig) -> State:
        """Pause for a human "yes" on destructive calls. No side effects here: LangGraph re-runs
        this node from the top when it resumes."""
        principal = principal_of(config)
        message = state["messages"][-1]
        requests = []
        for call in getattr(message, "tool_calls", []):
            action = actions.ACTIONS.get(call["name"])
            if not action or not action.destructive or not principal.can(action.permission):
                continue
            try:
                args = actions.parse_args(action, call["args"])
            except ValidationError:
                continue  # the tools node reports the invalid arguments
            summary = action.confirm_text(args) if action.confirm_text else action.name
            requests.append({"id": call["id"], "action": action.name, "summary": summary})
        if not requests:
            return {}
        answer = interrupt({"type": "confirm", "actions": requests})
        approved = answer if isinstance(answer, dict) else {}
        return {"approvals": {r["id"]: approved.get(r["id"]) is True for r in requests}}

    def tools(state: State, config: RunnableConfig) -> State:
        principal = principal_of(config)
        message = state["messages"][-1]
        approvals = state.get("approvals", {})
        results: list[AnyMessage] = []
        with deps.db.session() as session:
            for call in getattr(message, "tool_calls", []):
                action = actions.ACTIONS.get(call["name"])
                if action and action.destructive and call["id"] in approvals and not approvals[call["id"]]:
                    actions.record(
                        session,
                        principal,
                        call["name"],
                        call["args"],
                        "cancelled",
                        "Declined by the user",
                        via_assistant=True,
                    )
                    content = json.dumps(
                        {"error": "The staff member declined. It was NOT done. Do not retry."}
                    )
                    results.append(ToolMessage(content, tool_call_id=call["id"], name=call["name"]))
                    continue
                result = actions.execute(
                    session, principal, call["name"], call["args"], ctx, via_assistant=True
                )
                content = (
                    wrap_tool_output(result.data)
                    if result.ok
                    else json.dumps({"error": result.error, "outcome": result.outcome})
                )
                results.append(
                    ToolMessage(
                        content,
                        tool_call_id=call["id"],
                        name=call["name"],
                        status="success" if result.ok else "error",
                        artifact={"outcome": result.outcome},
                    )
                )
        return {"messages": results}

    def report(state: State) -> State:
        """After a change, code writes the reply from the real result. A small model summarising a
        refund can get it wrong ("now fully refunded"); a template can't."""
        lines = []
        for message in state["messages"][-len(last_calls(state)) :]:
            lines.append(describe_write(message))
        return {"messages": [AIMessage("\n".join(lines))]}

    def after_tools(state: State) -> str:
        calls = last_calls(state)
        if calls and all(getattr(actions.ACTIONS.get(c["name"]), "writes", False) for c in calls):
            return "report"
        return f"{state['route']}_agent"

    def guard_output(state: State) -> State:
        """Replace an answer that mentions ids or amounts no tool returned this turn."""
        answer = state["messages"][-1]
        turn = this_turn(state)
        evidence = "\n".join(str(m.content) for m in turn if isinstance(m, ToolMessage | HumanMessage))
        report = check_grounding(str(answer.content), evidence)
        if report.ok:
            return {}
        tool_results = [m for m in turn if isinstance(m, ToolMessage)]
        fallback = "I couldn't double-check my summary"
        fallback += f" (it mentioned {', '.join(report.unsupported[:3])}, which the system did not return)"
        if tool_results:
            fallback += ". Here is exactly what the system returned:\n" + "\n".join(
                f"- {m.name}: {_plain(m.content)}" for m in tool_results[-3:]
            )
        else:
            fallback += ". Please ask again with an order or ticket id."
        return {"messages": [AIMessage(fallback, id=answer.id)]}

    def knowledge(state: State) -> State:
        if deps.kb is None:
            return {"messages": [AIMessage("The help center is not available right now.")]}
        question = last_human(state)
        query = question
        if not question.isascii():  # multilingual: search with an English rewrite
            rewrite = deps.llm.invoke([SystemMessage(prompts.TRANSLATE), HumanMessage(question)])
            query = str(rewrite.content).strip() or question
        passages = deps.kb.search(query, limit=3, min_score=deps.kb_min_score)
        if not passages:
            return {
                "messages": [
                    AIMessage(
                        "I couldn't find that in the help center, so I won't guess. "
                        "Try rephrasing, or check with a manager."
                    )
                ]
            }
        numbered = "\n\n".join(f"[{i}] {p.heading}\n{p.text}" for i, p in enumerate(passages, 1))
        reply = deps.llm.bind(max_tokens=MAX_REPLY_TOKENS).invoke(
            [SystemMessage(prompts.KNOWLEDGE.format(passages=numbered)), HumanMessage(question)]
        )
        answer = str(reply.content).strip()
        evidence = numbered + "\n" + question
        cited = cited_sources(answer, len(passages))
        if not cited:
            match = best_supporting_passage(answer, [f"{p.heading} {p.text}" for p in passages])
            if match:
                answer, cited = f"{answer} [{match}]", [match]
        if not cited or not check_grounding(answer, evidence, numbers=True).ok:
            top = passages[0]
            answer = f"Here is what the help center says ({top.heading}):\n{top.text} [1]"
            cited = [1]
        sources = [
            {"n": i, "doc": p.doc, "heading": p.heading, "score": round(p.score, 2)}
            for i, p in enumerate(passages, 1)
            if i in cited
        ]
        return {"messages": [AIMessage(answer)], "sources": sources}

    def other(state: State, config: RunnableConfig) -> State:
        principal = principal_of(config)
        descriptions = [a.description for a in actions.actions_for(principal)]
        return {"messages": [AIMessage(prompts.capabilities(principal.name, descriptions))]}

    def after_specialist(state: State) -> str:
        last = state["messages"][-1]
        return "confirm" if getattr(last, "tool_calls", None) else "guard_output"

    graph = StateGraph(State)
    graph.add_node("guard_input", guard_input)
    graph.add_node("route", route)
    graph.add_node("orders_agent", make_specialist("orders"))
    graph.add_node("tickets_agent", make_specialist("tickets"))
    graph.add_node("confirm", confirm)
    graph.add_node("tools", tools)
    graph.add_node("report", report)
    graph.add_node("guard_output", guard_output)
    graph.add_node("knowledge", knowledge)
    graph.add_node("other", other)

    graph.add_edge(START, "guard_input")
    graph.add_conditional_edges("guard_input", lambda s: END if s.get("blocked") else "route")
    graph.add_conditional_edges(
        "route",
        lambda s: {"orders": "orders_agent", "tickets": "tickets_agent"}.get(s["route"], s["route"]),
        ["orders_agent", "tickets_agent", "knowledge", "other"],
    )
    for agent in ("orders_agent", "tickets_agent"):
        graph.add_conditional_edges(agent, after_specialist, ["confirm", "guard_output"])
    graph.add_edge("confirm", "tools")
    graph.add_conditional_edges("tools", after_tools, ["orders_agent", "tickets_agent", "report"])
    graph.add_edge("report", END)
    graph.add_edge("guard_output", END)
    graph.add_edge("knowledge", END)
    graph.add_edge("other", END)
    return graph.compile(checkpointer=checkpointer)


def last_calls(state: State) -> list[dict]:
    """Tool calls of the latest model message (the tools node answered each with one ToolMessage)."""
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage):
            return list(message.tool_calls or [])
    return []


def describe_write(message: AnyMessage) -> str:
    """One plain sentence about what a write action really did, built from its result."""
    try:
        data = json.loads(str(message.content))
    except ValueError:
        return str(message.content)[:300]
    if "error" in data:
        if "declined" in data["error"]:
            return "OK, I did not do it."
        return f"That was not done: {data['error']}"
    result = data.get("result", {})
    if not isinstance(result, dict):
        return "Done."
    if result.get("note"):
        details = f"Status: {result.get('status')}. Refunded so far: {result.get('refunded')}"
        return f"{result['note']} {details}, still refundable: {result.get('refundable')}."
    if str(result.get("id", "")).startswith("TCK-"):
        return (
            f"Done: ticket {result['id']} for {result.get('customer')} is {result.get('status')}, "
            f"priority {result.get('priority')}."
        )
    return "Done."


def _plain(content: Any) -> str:
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return str(content)[:300]
    data = data.get("result", data)
    if isinstance(data, dict) and "id" in data:
        keys = ("id", "status", "total", "refunded", "refundable", "priority", "subject")
        return ", ".join(f"{k}: {data[k]}" for k in keys if k in data)
    if isinstance(data, list):
        return (
            "; ".join(
                str(d.get("id", d)) + (f" ({d.get('status')})" if isinstance(d, dict) else "")
                for d in data[:10]
            )
            or "nothing found"
        )
    return str(data)[:300]


def new_thread_id(user_id: int) -> str:
    """Threads carry their owner, so one user can never resume another user's conversation."""
    return f"u{user_id}-{uuid.uuid4().hex}"


def owns_thread(user_id: int, thread_id: str) -> bool:
    return thread_id.startswith(f"u{user_id}-")
