"""REST API of the support desk itself. Write routes go through the same action catalogue as the
assistant, so a person clicking a button and the AI follow exactly the same rules."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import ServicesDep, UserDep, require_permission
from app.models import AuditLog
from app.security import Permission
from app.services import actions, orders, tickets
from app.services.errors import NotFound

router = APIRouter(prefix="/api", tags=["desk"])

STATUS_FOR = {"denied": 403, "not_found": 404, "rejected": 409, "invalid": 422}


def run(svc: ServicesDep, user: UserDep, name: str, args: dict) -> Any:
    ctx = actions.ActionContext(support_refund_limit=svc.settings.support_refund_limit)
    with svc.db.session() as session:
        result = actions.execute(session, user, name, args, ctx, via_assistant=False)
    if not result.ok:
        raise HTTPException(STATUS_FOR.get(result.outcome, 400), result.error)
    return result.data


@router.get("/stats")
def stats(svc: ServicesDep, user: UserDep) -> dict:
    with svc.db.session() as session:
        return {
            "orders": orders.order_stats(session, user),
            "tickets": tickets.ticket_stats(session, user),
        }


@router.get("/orders")
def list_orders(
    svc: ServicesDep,
    user: UserDep,
    status_: str | None = Query(None, alias="status"),
    email: str | None = None,
    limit: int = Query(20, ge=1, le=50),
) -> list[dict]:
    with svc.db.session() as session:
        return orders.search_orders(session, user, email, status_, limit)


@router.get("/orders/{order_id}")
def get_order(order_id: str, svc: ServicesDep, user: UserDep) -> dict:
    with svc.db.session() as session:
        try:
            return orders.get_order(session, user, order_id)
        except NotFound as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, body: dict, svc: ServicesDep, user: UserDep) -> dict:
    return run(svc, user, "cancel_order", {**body, "order_id": order_id})


@router.post("/orders/{order_id}/refund")
def refund_order(order_id: str, body: dict, svc: ServicesDep, user: UserDep) -> dict:
    return run(svc, user, "refund_order", {**body, "order_id": order_id})


@router.get("/tickets")
def list_tickets(
    svc: ServicesDep,
    user: UserDep,
    status_: str | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=50),
) -> list[dict]:
    with svc.db.session() as session:
        return tickets.search_tickets(session, user, status_, None, None, limit)


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: str, body: dict, svc: ServicesDep, user: UserDep) -> dict:
    return run(svc, user, "update_ticket", {**body, "ticket_id": ticket_id})


@router.get("/audit", dependencies=[require_permission(Permission.AUDIT_READ)])
def audit(svc: ServicesDep, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    with svc.db.session() as session:
        rows = session.scalars(
            select(AuditLog).options(selectinload(AuditLog.user)).order_by(AuditLog.id.desc()).limit(limit)
        )
        return [
            {
                "id": r.id,
                "user": r.user.name,
                "action": r.action,
                "args": r.args,
                "outcome": r.outcome,
                "detail": r.detail,
                "via_assistant": r.via_assistant,
                "created_at": r.created_at.isoformat() + "Z",
            }
            for r in rows
        ]
