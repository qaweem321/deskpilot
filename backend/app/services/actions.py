"""The catalogue of actions staff can take, used by BOTH the REST API and the AI assistant.

Each action declares its permission, whether it changes data, and whether it is destructive
(needs an explicit "yes" before it runs). Arguments are validated with Pydantic, so the model
cannot pass anything the API would not accept from a human.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.security import Permission, PermissionDenied, Principal
from app.services import orders, tickets
from app.services.errors import InvalidAction, NotFound
from app.services.formatting import money

ORDER_PATTERN = r"^[Oo][Rr][Dd]-\d{4,6}$"
TICKET_PATTERN = r"^[Tt][Cc][Kk]-\d{4,6}$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def order_id_field(**kw: Any) -> Any:
    return Field(pattern=ORDER_PATTERN, description="Order id, e.g. ORD-1042", **kw)


def email_field(**kw: Any) -> Any:
    return Field(pattern=EMAIL_PATTERN, max_length=200, description="Customer email", **kw)


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GetOrder(Args):
    order_id: str = order_id_field()


class SearchOrders(Args):
    customer_email: str | None = email_field(default=None)
    status: Literal[orders.ORDER_STATUSES] | None = None  # type: ignore[valid-type]
    limit: int = Field(default=5, ge=1, le=20)


class CancelOrder(Args):
    order_id: str = order_id_field()
    reason: str = Field(min_length=3, max_length=300)


class RefundOrder(Args):
    order_id: str = order_id_field()
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2, description="Amount in USD")
    reason: str = Field(min_length=3, max_length=300)


class GetTicket(Args):
    ticket_id: str = Field(pattern=TICKET_PATTERN, description="Ticket id, e.g. TCK-2003")


class SearchTickets(Args):
    status: Literal[tickets.TICKET_STATUSES] | None = None  # type: ignore[valid-type]
    customer_email: str | None = email_field(default=None)
    order_id: str | None = order_id_field(default=None)
    limit: int = Field(default=5, ge=1, le=20)


class CreateTicket(Args):
    customer_email: str = email_field()
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=4000)
    priority: Literal[tickets.PRIORITIES] = "normal"  # type: ignore[valid-type]
    order_id: str | None = order_id_field(default=None)


class UpdateTicket(Args):
    ticket_id: str = Field(pattern=TICKET_PATTERN, description="Ticket id, e.g. TCK-2003")
    status: Literal[tickets.TICKET_STATUSES] | None = None  # type: ignore[valid-type]
    priority: Literal[tickets.PRIORITIES] | None = None  # type: ignore[valid-type]


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    group: Literal["orders", "tickets"]
    permission: Permission
    args_model: type[Args]
    run: Callable[[Session, Principal, Any, "ActionContext"], Any]
    writes: bool = False
    destructive: bool = False
    confirm_text: Callable[[Any], str] | None = None


@dataclass(frozen=True)
class ActionContext:
    support_refund_limit: Decimal


ACTIONS: dict[str, Action] = {
    a.name: a
    for a in [
        Action(
            "get_order",
            "Look up one order by its id: status, total, items, refunds.",
            "orders",
            Permission.ORDERS_READ,
            GetOrder,
            lambda s, p, a, _: orders.get_order(s, p, a.order_id),
        ),
        Action(
            "search_orders",
            "List recent orders, filtered by customer email and/or status.",
            "orders",
            Permission.ORDERS_READ,
            SearchOrders,
            lambda s, p, a, _: orders.search_orders(s, p, a.customer_email, a.status, a.limit),
        ),
        Action(
            "cancel_order",
            "Cancel an order that has not shipped yet (status pending).",
            "orders",
            Permission.ORDERS_CANCEL,
            CancelOrder,
            lambda s, p, a, _: orders.cancel_order(s, p, a.order_id, a.reason),
            writes=True,
            destructive=True,
            confirm_text=lambda a: f"Cancel order {a.order_id.upper()} ({a.reason})",
        ),
        Action(
            "refund_order",
            "Refund part or all of a shipped or delivered order. Amount in USD.",
            "orders",
            Permission.ORDERS_REFUND,
            RefundOrder,
            lambda s, p, a, ctx: orders.refund_order(
                s, p, a.order_id, a.amount, a.reason, ctx.support_refund_limit
            ),
            writes=True,
            destructive=True,
            confirm_text=lambda a: f"Refund {money(a.amount)} on order {a.order_id.upper()} ({a.reason})",
        ),
        Action(
            "get_ticket",
            "Read one support ticket by its id.",
            "tickets",
            Permission.TICKETS_READ,
            GetTicket,
            lambda s, p, a, _: tickets.get_ticket(s, p, a.ticket_id),
        ),
        Action(
            "search_tickets",
            "List recent tickets, filtered by status, customer email and/or order id.",
            "tickets",
            Permission.TICKETS_READ,
            SearchTickets,
            lambda s, p, a, _: tickets.search_tickets(s, p, a.status, a.customer_email, a.order_id, a.limit),
        ),
        Action(
            "create_ticket",
            "Open a new support ticket for a customer (by email), optionally about one order.",
            "tickets",
            Permission.TICKETS_WRITE,
            CreateTicket,
            lambda s, p, a, _: tickets.create_ticket(
                s, p, a.customer_email, a.subject, a.body, a.priority, a.order_id
            ),
            writes=True,
        ),
        Action(
            "update_ticket",
            "Change a ticket's status (open, pending, closed) and/or priority.",
            "tickets",
            Permission.TICKETS_WRITE,
            UpdateTicket,
            lambda s, p, a, _: tickets.update_ticket(s, p, a.ticket_id, a.status, a.priority),
            writes=True,
        ),
    ]
}


def actions_for(principal: Principal, group: str | None = None) -> list[Action]:
    """Only the actions this user may take. The model never even sees the others."""
    return [
        a for a in ACTIONS.values() if principal.can(a.permission) and (group is None or a.group == group)
    ]


@dataclass
class ActionResult:
    ok: bool
    outcome: str  # done, denied, rejected, invalid, not_found
    data: Any = None
    error: str = ""


def parse_args(action: Action, raw: dict) -> Args:
    return action.args_model.model_validate(raw)


def execute(
    session: Session,
    principal: Principal,
    name: str,
    raw_args: dict,
    ctx: ActionContext,
    via_assistant: bool,
) -> ActionResult:
    """Validate, authorise, run and audit one action. Never raises for expected failures."""
    action = ACTIONS.get(name)
    if action is None:
        result = ActionResult(False, "invalid", error=f"There is no action called {name}.")
    else:
        try:
            args = parse_args(action, raw_args)
            # A savepoint, so a failed action never undoes earlier work in the same request.
            with session.begin_nested():
                data = action.run(session, principal, args, ctx)
            result = ActionResult(True, "done", data=data)
        except ValidationError as exc:
            errors = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            result = ActionResult(False, "invalid", error=f"Invalid arguments: {errors}")
        except PermissionDenied as exc:
            result = ActionResult(False, "denied", error=str(exc))
        except NotFound as exc:
            result = ActionResult(False, "not_found", error=str(exc))
        except InvalidAction as exc:
            result = ActionResult(False, "rejected", error=str(exc))

    writes = action.writes if action else False
    if via_assistant or writes or result.outcome == "denied":
        record(session, principal, name, raw_args, result.outcome, result.error, via_assistant)
    return result


def record(
    session: Session,
    principal: Principal,
    action: str,
    args: dict,
    outcome: str,
    detail: str = "",
    via_assistant: bool = False,
) -> None:
    session.add(
        AuditLog(
            user_id=principal.id,
            action=action[:50],
            args=_jsonable(args),
            outcome=outcome,
            detail=detail[:500],
            via_assistant=via_assistant,
        )
    )
    session.flush()


def _jsonable(args: dict) -> dict:
    return {
        str(k)[:50]: (v if isinstance(v, int | float | bool | None) else str(v)[:300])
        for k, v in args.items()
    }
