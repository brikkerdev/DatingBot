from aiogram import Router

from .browse import router as browse_router
from .chat import router as chat_router
from .edit_profile import router as edit_profile_router
from .matches import router as matches_router
from .menu import router as menu_router
from .registration import router as registration_router
from .start import router as start_router

router = Router()
router.include_router(start_router)
router.include_router(registration_router)
router.include_router(edit_profile_router)
router.include_router(browse_router)
router.include_router(matches_router)
router.include_router(chat_router)
router.include_router(menu_router)
