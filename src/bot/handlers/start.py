from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.reply import main_menu_keyboard, remove_keyboard
from src.bot.states.registration import RegistrationState
from src.services.profile import get_profile_by_user_id
from src.services.user import get_or_create_user

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()

    user, is_new = await get_or_create_user(session, message.from_user.id)

    if not is_new:
        profile = await get_profile_by_user_id(session, user.id)
        if profile:
            await message.answer(
                f"С возвращением, {profile.name}!",
                reply_markup=main_menu_keyboard(),
            )
            return

    await state.update_data(user_id=user.id)
    await state.set_state(RegistrationState.waiting_for_name)
    await message.answer(
        "Добро пожаловать в Dating Bot!\n\n"
        "Давайте создадим вашу анкету.\n"
        "Как вас зовут?",
        reply_markup=remove_keyboard,
    )
