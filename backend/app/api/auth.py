from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.deps import COOKIE, ServicesDep, UserDep
from app.models import User
from app.security import ROLE_PERMISSIONS, create_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, svc: ServicesDep) -> dict:
    email = body.email.strip().lower()
    # Limit by address and by IP: stops guessing one account and spraying many.
    if not (
        svc.login_limiter.allow(f"email:{email}") and svc.login_limiter.allow(f"ip:{client_ip(request)}")
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait a minute and try again."
        )
    with svc.db.session() as session:
        user = session.scalar(select(User).where(func.lower(User.email) == email))
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password.")
        token = create_token(user.id, svc.settings.jwt_secret, svc.settings.jwt_ttl_minutes)
        response.set_cookie(
            COOKIE,
            token,
            max_age=svc.settings.jwt_ttl_minutes * 60,
            httponly=True,
            secure=svc.settings.cookie_secure,
            samesite="strict",
            path="/",
        )
        return {"name": user.name, "role": user.role}


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


@router.get("/me")
def me(user: UserDep) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role.value,
        "permissions": sorted(p.value for p in ROLE_PERMISSIONS[user.role]),
    }
