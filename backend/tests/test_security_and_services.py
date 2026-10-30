from decimal import Decimal

import pytest

from app.db import Database
from app.security import (
    Permission,
    PermissionDenied,
    Principal,
    Role,
    create_token,
    hash_password,
    read_token,
    verify_password,
)
from app.seed import seed
from app.services import orders, tickets
from app.services.errors import InvalidAction, NotFound

SUPPORT = Principal(2, "Sam", Role.SUPPORT)
MANAGER = Principal(3, "Maya", Role.MANAGER)
VIEWER = Principal(1, "Vera", Role.VIEWER)


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(f"sqlite:///{tmp_path}/s.db")
    database.create_all()
    seed(database)
    return database


def test_password_hashing():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", "garbage")


def test_token_round_trip_and_tampering():
    token = create_token(7, "s" * 40, 5)
    assert read_token(token, "s" * 40) == 7
    assert read_token(token, "t" * 40) is None
    assert read_token(token + "x", "s" * 40) is None


def test_role_permissions():
    assert VIEWER.can(Permission.ORDERS_READ) and not VIEWER.can(Permission.ORDERS_REFUND)
    assert SUPPORT.can(Permission.ORDERS_REFUND) and not SUPPORT.can(Permission.AUDIT_READ)
    assert all(MANAGER.can(p) for p in Permission)


def test_seed_runs_once(db):
    assert seed(db) is False


def test_viewer_cannot_refund(db):
    with db.session() as s, pytest.raises(PermissionDenied):
        orders.refund_order(s, VIEWER, "ORD-1002", 10, "test", 50)


def test_support_refund_limit(db):
    with db.session() as s:
        with pytest.raises(InvalidAction, match="up to \\$50.00"):
            orders.refund_order(s, SUPPORT, "ORD-1002", 60, "torn seam", 50)
        view = orders.refund_order(s, SUPPORT, "ORD-1002", 50, "torn seam", 50)
        assert view["refunded"] == "$50.00"
        # A manager has no limit.
        view = orders.refund_order(s, MANAGER, "ORD-1002", 99, "replacement sent", 50)
        assert view["status"] == "refunded" and view["refundable"] == "$0.00"


def test_cannot_refund_more_than_paid(db):
    with db.session() as s:
        # ORD-1006 = 64.95 + 24.99 + 18.00 = 107.94, with 24.99 already refunded.
        assert orders.get_order(s, MANAGER, "ORD-1006")["refundable"] == "$82.95"
        with pytest.raises(InvalidAction, match="Only \\$82.95"):
            orders.refund_order(s, MANAGER, "ORD-1006", Decimal("82.96"), "x" * 5, 50)


def test_pending_orders_cancel_not_refund(db):
    with db.session() as s:
        with pytest.raises(InvalidAction, match="cancel it instead"):
            orders.refund_order(s, MANAGER, "ORD-1001", 5, "nope", 50)
        assert orders.cancel_order(s, SUPPORT, "ord-1001", "changed mind")["status"] == "cancelled"
        with pytest.raises(InvalidAction, match="only pending"):
            orders.cancel_order(s, SUPPORT, "ORD-1001", "again")


def test_missing_order(db):
    with db.session() as s, pytest.raises(NotFound):
        orders.get_order(s, VIEWER, "ORD-9999")


def test_ticket_must_match_customer_order(db):
    with db.session() as s:
        with pytest.raises(InvalidAction, match="does not belong"):
            tickets.create_ticket(s, SUPPORT, "sara@example.com", "Late", "Where?", "normal", "ORD-1004")
        t = tickets.create_ticket(s, SUPPORT, "SARA@example.com", "Late", "Where?", "high", "ORD-1002")
        assert t["id"] == "TCK-2006" and t["priority"] == "high"


def test_search_orders_by_email_is_case_insensitive(db):
    with db.session() as s:
        found = orders.search_orders(s, VIEWER, customer_email="Sara@Example.com", limit=20)
        assert {"ORD-1001", "ORD-1002"} <= {o["id"] for o in found}
