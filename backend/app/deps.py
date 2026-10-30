"""Request dependencies: the app's shared services and the signed-in user."""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings
from app.db import Database
from app.models import User
from app.ratelimit import RateLimiter
from app.security import Permission, Principal, Role, read_token

COOKIE = "deskpilot_session"


@dataclass
class Services:
    settings: Settings
    db: Database
    graph: Any
    login_limiter: RateLimiter
    chat_limiter: RateLimiter
    voice: Any = None


def services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(services)]


def current_user(request: Request, svc: ServicesDep) -> Principal:
    token = request.cookies.get(COOKIE)
    user_id = read_token(token, svc.settings.jwt_secret) if token else None
    if user_id is not None:
        with svc.db.session() as session:
            user = session.get(User, user_id)
            if user is not None:
                return Principal(id=user.id, name=user.name, role=Role(user.role))
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in again.")


UserDep = Annotated[Principal, Depends(current_user)]


def require_permission(permission: Permission):  # noqa: ANN201
    def check(user: UserDep) -> Principal:
        if not user.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role can't do that.")
        return user

    return Depends(check)
