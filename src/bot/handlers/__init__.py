from aiogram import Router

from .menu import router as menu_router
from .registration import router as registration_router
from .start import router as start_router

router = Router()
router.include_router(start_router)
router.include_router(registration_router)
router.include_router(menu_router)
