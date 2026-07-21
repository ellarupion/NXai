import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.services.admin import AdminService
from interfaces.api.auth import CurrentAdmin, create_access_token, get_current_admin
from interfaces.api.deps import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Простой in-memory rate limit логина по IP (аудит, п.3.4): скользящее окно,
# защита от перебора пароля. Панель — один процесс api, поэтому общего Redis
# для этого не нужно; при переезде на несколько воркеров вынести в Redis.
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _check_login_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    window_start = now - LOGIN_WINDOW_SECONDS
    attempts = [t for t in _login_attempts[client_ip] if t >= window_start]
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        logger.warning("auth.login_rate_limited", client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа — подождите несколько минут",
        )
    attempts.append(now)
    _login_attempts[client_ip] = attempts


class LoginPayload(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    username: str
    is_superadmin: bool


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginPayload, request: Request, session: AsyncSession = Depends(get_db)
) -> TokenOut:
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)
    admin = await AdminService(session).verify_password(payload.username, payload.password)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    token = create_access_token(admin.id, admin.username, admin.is_superadmin)
    return TokenOut(access_token=token)


@router.get("/me", response_model=MeOut)
async def me(current: CurrentAdmin = Depends(get_current_admin)) -> MeOut:
    return MeOut(username=current.username, is_superadmin=current.is_superadmin)
