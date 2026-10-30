"""Ticket rules. Ticket text is written by customers, so treat it as untrusted data everywhere."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, Order, Ticket
from app.security import Permission, Principal, require
from app.services.errors import InvalidAction, NotFound
from app.services.formatting import day

TICKET_STATUSES = ("open", "pending", "closed")
PRIORITIES = ("low", "normal", "high", "urgent")


def ticket_view(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "customer": ticket.customer.name,
        "customer_email": ticket.customer.email,
        "order_id": ticket.order_id,
        "subject": ticket.subject,
        "body": ticket.body,
        "status": ticket.status,
        "priority": ticket.priority,
        "opened_on": day(ticket.created_at),
        "created_at": ticket.created_at.isoformat() + "Z",
    }


def _load(session: Session, ticket_id: str) -> Ticket:
    ticket = session.scalar(
        select(Ticket).where(Ticket.id == ticket_id.strip().upper()).options(selectinload(Ticket.customer))
    )
    if ticket is None:
        raise NotFound(f"Ticket {ticket_id} does not exist.")
    return ticket


def get_ticket(session: Session, principal: Principal, ticket_id: str) -> dict:
    require(principal, Permission.TICKETS_READ)
    return ticket_view(_load(session, ticket_id))


def search_tickets(
    session: Session,
    principal: Principal,
    status: str | None = None,
    customer_email: str | None = None,
    order_id: str | None = None,
    limit: int = 10,
) -> list[dict]:
    require(principal, Permission.TICKETS_READ)
    query = (
        select(Ticket)
        .options(selectinload(Ticket.customer))
        .order_by(Ticket.created_at.desc())
        .limit(max(1, min(limit, 50)))
    )
    if status:
        query = query.where(Ticket.status == status)
    if customer_email:
        query = query.join(Customer).where(func.lower(Customer.email) == customer_email.lower())
    if order_id:
        query = query.where(Ticket.order_id == order_id.strip().upper())
    return [ticket_view(t) for t in session.scalars(query)]


def _next_ticket_id(session: Session) -> str:
    last = session.scalar(select(func.max(Ticket.id)))
    number = int(last.split("-")[1]) + 1 if last else 2001
    return f"TCK-{number}"


def create_ticket(
    session: Session,
    principal: Principal,
    customer_email: str,
    subject: str,
    body: str,
    priority: str = "normal",
    order_id: str | None = None,
) -> dict:
    require(principal, Permission.TICKETS_WRITE)
    customer = session.scalar(
        select(Customer).where(func.lower(Customer.email) == customer_email.strip().lower())
    )
    if customer is None:
        raise NotFound(f"No customer with the email {customer_email}.")
    if order_id:
        order = session.get(Order, order_id.strip().upper())
        if order is None or order.customer_id != customer.id:
            raise InvalidAction(f"Order {order_id} does not belong to {customer.email}.")
        order_id = order.id
    ticket = Ticket(
        id=_next_ticket_id(session),
        customer=customer,
        order_id=order_id,
        subject=subject[:200],
        body=body[:4000],
        status="open",
        priority=priority,
    )
    session.add(ticket)
    session.flush()
    return ticket_view(ticket)


def update_ticket(
    session: Session,
    principal: Principal,
    ticket_id: str,
    status: str | None = None,
    priority: str | None = None,
) -> dict:
    require(principal, Permission.TICKETS_WRITE)
    if status is None and priority is None:
        raise InvalidAction("Say what to change: the status, the priority or both.")
    ticket = _load(session, ticket_id)
    if status:
        ticket.status = status
    if priority:
        ticket.priority = priority
    session.flush()
    return ticket_view(ticket)


def ticket_stats(session: Session, principal: Principal) -> dict:
    require(principal, Permission.TICKETS_READ)
    rows = session.execute(select(Ticket.status, func.count()).group_by(Ticket.status)).all()
    return {status: count for status, count in rows}
