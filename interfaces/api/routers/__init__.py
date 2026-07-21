from fastapi import APIRouter

from interfaces.api.routers.auth import router as auth_router
from interfaces.api.routers.candidates import router as candidates_router
from interfaces.api.routers.channel_bots import router as channel_bots_router
from interfaces.api.routers.health import router as health_router
from interfaces.api.routers.settings import router as settings_router
from interfaces.api.routers.source_channels import router as source_channels_router
from interfaces.api.routers.target_channels import router as target_channels_router
from interfaces.api.routers.telethon_sessions import router as telethon_sessions_router
from interfaces.api.routers.themes import router as themes_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(themes_router)
router.include_router(source_channels_router)
router.include_router(target_channels_router)
router.include_router(channel_bots_router)
router.include_router(settings_router)
router.include_router(telethon_sessions_router)
router.include_router(candidates_router)
