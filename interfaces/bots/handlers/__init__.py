from aiogram import Router

from interfaces.bots.handlers.ad_watchdog import router as ad_watchdog_router
from interfaces.bots.handlers.admin_start import router as admin_start_router

router = Router(name="nxai-channel-bot")
router.include_router(admin_start_router)
router.include_router(ad_watchdog_router)
