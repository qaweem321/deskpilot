"""Order rules: lookups, cancellations and refunds. REST routes and the assistant both call these."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, Order, Refund
from app.security import Permission, Principal, Role, require
from app.services.errors import InvalidAction, NotFound
from app.services.formatting import day, money, to_cents

ORDER_STATUSES = ("pending", "shipped", "delivered", "cancelled", "refunded")


def _refunded(order: Order) -> Decimal:
    return sum((r.amount for r in order.refunds), Decimal("0"))


def order_view(order: Order) -> dict:
    refunded = _refunded(order)
    return {
        "id": order.id,
        "customer": order.customer.name,
        "customer_email": order.customer.email,
        "status": order.status,
        "total": money(order.total),
        "refunded": money(refunded),
        "refundable": money(order.total - refunded),
        "items": order.items,
        "placed_on": day(order.created_at),
        "created_at": order.created_at.isoformat() + "Z",
    }


def _load(session: Session, order_id: str) -> Order:
    order = session.scalar(
        select(Order)
        .where(Order.id == order_id.strip().upper())
        .options(selectinload(Order.customer), selectinload(Order.refunds))
    )
    if order is None:
        raise NotFound(f"Order {order_id} does not exist.")
    return order


def get_order(session: Session, principal: Principal, order_id: str) -> dict:
    require(principal, Permission.ORDERS_READ)
    return order_view(_load(session, order_id))


def search_orders(
    session: Session,
    principal: Principal,
    customer_email: str | None = None,
    status: str | None = None,
    limit: int = 10,
) -> list[dict]:
    require(principal, Permission.ORDERS_READ)
    query = (
        select(Order)
        .options(selectinload(Order.customer), selectinload(Order.refunds))
        .order_by(Order.created_at.desc())
        .limit(max(1, min(limit, 50)))
    )
    if customer_email:
        query = query.join(Customer).where(func.lower(Customer.email) == customer_email.lower())
    if status:
        query = query.where(Order.status == status)
    return [order_view(o) for o in session.scalars(query)]


def cancel_order(session: Session, principal: Principal, order_id: str, reason: str) -> dict:
    require(principal, Permission.ORDERS_CANCEL)
    order = _load(session, order_id)
    if order.status != "pending":
        raise InvalidAction(f"Order {order.id} is {order.status}; only pending orders can be cancelled.")
    order.status = "cancelled"
    session.flush()
    # Spelled out so a summarising model can't claim more happened than did.
    return {**order_view(order), "note": "Order cancelled. No refund was issued by this action."}


def refund_order(
    session: Session,
    principal: Principal,
    order_id: str,
    amount: Decimal | float,
    reason: str,
    support_limit: Decimal | float,
) -> dict:
    require(principal, Permission.ORDERS_REFUND)
    amount = to_cents(amount)
    if amount <= 0:
        raise InvalidAction("The refund amount must be more than $0.00.")
    if principal.role == Role.SUPPORT and amount > to_cents(support_limit):
        raise InvalidAction(
            f"Support staff can refund up to {money(support_limit)}. Ask a manager for {money(amount)}."
        )
    # Lock-free but safe on SQLite (one writer at a time); on Postgres use SELECT ... FOR UPDATE.
    order = _load(session, order_id)
    if order.status == "pending":
        raise InvalidAction(f"Order {order.id} has not shipped yet; cancel it instead of refunding.")
    remaining = order.total - _refunded(order)
    if amount > remaining:
        raise InvalidAction(f"Only {money(remaining)} of order {order.id} can still be refunded.")
    order.refunds.append(
        Refund(order_id=order.id, amount=amount, reason=reason[:300], created_by=principal.id)
    )
    if amount == remaining:
        order.status = "refunded"
    session.flush()
    return {**order_view(order), "note": f"Refunded {money(amount)} on {order.id}."}


def order_stats(session: Session, principal: Principal) -> dict:
    require(principal, Permission.ORDERS_READ)
    rows = session.execute(select(Order.status, func.count()).group_by(Order.status)).all()
    return {status: count for status, count in rows}
