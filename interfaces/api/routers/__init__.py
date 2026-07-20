from fastapi import APIRouter

from interfaces.api.routers.auth import router as auth_router
from interfaces.api.routers.health import router as health_router
from interfaces.api.routers.source_channels import router as source_channels_router
from interfaces.api.routers.themes import router as themes_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(themes_router)
router.include_router(source_channels_router)
