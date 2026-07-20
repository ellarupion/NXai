from aiogram import Router

from interfaces.bots.handlers.ad_watchdog import router as ad_watchdog_router

router = Router(name="nxai-channel-bot")
router.include_router(ad_watchdog_router)
