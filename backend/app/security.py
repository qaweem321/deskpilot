"""Passwords, tokens and role-based permissions. Every rule about "who may do what" lives here."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt


class Role(StrEnum):
    VIEWER = "viewer"
    SUPPORT = "support"
    MANAGER = "manager"


class Permission(StrEnum):
    ORDERS_READ = "orders.read"
    ORDERS_CANCEL = "orders.cancel"
    ORDERS_REFUND = "orders.refund"
    TICKETS_READ = "tickets.read"
    TICKETS_WRITE = "tickets.write"
    AUDIT_READ = "audit.read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.ORDERS_READ, Permission.TICKETS_READ}),
    Role.SUPPORT: frozenset(
        {
            Permission.ORDERS_READ,
            Permission.ORDERS_CANCEL,
            Permission.ORDERS_REFUND,  # capped by SUPPORT_REFUND_LIMIT in the order service
            Permission.TICKETS_READ,
            Permission.TICKETS_WRITE,
        }
    ),
    Role.MANAGER: frozenset(Permission),
}


@dataclass(frozen=True)
class Principal:
    """The signed-in staff member. The assistant always acts as this person, never as itself."""

    id: int
    name: str
    role: Role

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]


class PermissionDenied(Exception):
    pass


def require(principal: Principal, permission: Permission) -> None:
    if not principal.can(permission):
        raise PermissionDenied(f"Your role ({principal.role}) is not allowed to do {permission}.")


# scrypt from the standard library: no extra dependency, memory-hard.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_token(user_id: int, secret: str, ttl_minutes: int) -> str:
    # Only the user id goes in the token: the role is read from the database on every request,
    # so a demoted user loses rights at once instead of when the token expires.
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=ttl_minutes)}
    return jwt.encode(payload, secret, algorithm="HS256")


def read_token(token: str, secret: str) -> int | None:
    try:
        data = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        return int(data["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
