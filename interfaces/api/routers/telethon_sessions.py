"""Пул Telethon-читалок — веб-логин по шагам (core/services/telethon_login.py)
и CRUD уже созданных сессий. gated require_superadmin целиком: это буквально
вход в личные Telegram-аккаунты пула, самый чувствительный секрет в проекте
после ключей LLM."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.telethon_session import TelethonSession
from core.services.effective_settings import get_effective_settings
from core.services.telethon_login import (
    PasswordRequiredError,
    TelethonLoginError,
    start_login,
    submit_code,
    submit_password,
)
from interfaces.api.auth import require_superadmin
from interfaces.api.deps import get_db

router = APIRouter(
    prefix="/telethon-sessions", tags=["telethon-sessions"], dependencies=[Depends(require_superadmin)]
)


class TelethonSessionOut(BaseModel):
    id: UUID
    label: str
    is_active: bool

    model_config = {"from_attributes": True}


class TelethonSessionUpdate(BaseModel):
    label: str | None = None
    is_active: bool | None = None


class LoginStartPayload(BaseModel):
    phone_number: str
    label: str


class LoginStartOut(BaseModel):
    attempt_id: str


class LoginCodePayload(BaseModel):
    attempt_id: str
    code: str


class LoginPasswordPayload(BaseModel):
    attempt_id: str
    password: str


class LoginStepOut(BaseModel):
    status: str  # "password_required" | "done"
    telethon_session: TelethonSessionOut | None = None


@router.get("", response_model=list[TelethonSessionOut])
async def list_telethon_sessions(session: AsyncSession = Depends(get_db)) -> list[TelethonSession]:
    result = await session.execute(select(TelethonSession).order_by(TelethonSession.created_at))
    return list(result.scalars().all())


@router.put("/{telethon_session_id}", response_model=TelethonSessionOut)
async def update_telethon_session(
    telethon_session_id: UUID, payload: TelethonSessionUpdate, session: AsyncSession = Depends(get_db)
) -> TelethonSession:
    telethon_session = await session.get(TelethonSession, telethon_session_id)
    if telethon_session is None:
        raise HTTPException(status_code=404, detail="TelethonSession not found")
    if payload.label is not None:
        telethon_session.label = payload.label
    if payload.is_active is not None:
        telethon_session.is_active = payload.is_active
    await session.flush()
    await session.commit()
    return telethon_session


@router.delete("/{telethon_session_id}", status_code=204)
async def delete_telethon_session(telethon_session_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    """ingest_session_id у затронутых source_channels уходит в NULL (ON DELETE
    SET NULL, см. core/models/source_channel.py) — сами каналы не пропадают,
    просто временно остаются без читающего аккаунта."""
    telethon_session = await session.get(TelethonSession, telethon_session_id)
    if telethon_session is None:
        return
    await session.delete(telethon_session)
    await session.commit()


@router.post("/login/start", response_model=LoginStartOut)
async def start_login_endpoint(
    payload: LoginStartPayload, session: AsyncSession = Depends(get_db)
) -> LoginStartOut:
    settings = await get_effective_settings(session)
    try:
        attempt_id = await start_login(payload.phone_number, payload.label, settings)
    except TelethonLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoginStartOut(attempt_id=attempt_id)


@router.post("/login/code", response_model=LoginStepOut)
async def submit_code_endpoint(
    payload: LoginCodePayload, session: AsyncSession = Depends(get_db)
) -> LoginStepOut:
    settings = await get_effective_settings(session)
    try:
        result = await submit_code(payload.attempt_id, payload.code, settings)
    except PasswordRequiredError:
        return LoginStepOut(status="password_required")
    except TelethonLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    telethon_session = TelethonSession(label=result.label, session_string=result.session_string)
    session.add(telethon_session)
    await session.flush()
    await session.commit()
    return LoginStepOut(status="done", telethon_session=TelethonSessionOut.model_validate(telethon_session))


@router.post("/login/password", response_model=LoginStepOut)
async def submit_password_endpoint(
    payload: LoginPasswordPayload, session: AsyncSession = Depends(get_db)
) -> LoginStepOut:
    settings = await get_effective_settings(session)
    try:
        result = await submit_password(payload.attempt_id, payload.password, settings)
    except TelethonLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    telethon_session = TelethonSession(label=result.label, session_string=result.session_string)
    session.add(telethon_session)
    await session.flush()
    await session.commit()
    return LoginStepOut(status="done", telethon_session=TelethonSessionOut.model_validate(telethon_session))
