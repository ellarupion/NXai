from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.admin import AdminService
from interfaces.api.auth import CurrentAdmin, create_access_token, get_current_admin
from interfaces.api.deps import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


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
async def login(payload: LoginPayload, session: AsyncSession = Depends(get_db)) -> TokenOut:
    admin = await AdminService(session).verify_password(payload.username, payload.password)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    token = create_access_token(admin.id, admin.username, admin.is_superadmin)
    return TokenOut(access_token=token)


@router.get("/me", response_model=MeOut)
async def me(current: CurrentAdmin = Depends(get_current_admin)) -> MeOut:
    return MeOut(username=current.username, is_superadmin=current.is_superadmin)
