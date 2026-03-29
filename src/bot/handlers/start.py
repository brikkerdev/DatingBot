from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.reply import main_menu_keyboard, remove_keyboard
from src.bot.states.registration import RegistrationState
from src.services.profile import get_profile_by_user_id
from src.services.referral import create_referral, get_referral_count
from src.services.user import get_or_create_user, get_user_by_telegram_id

router = Router()


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Handle /start ref_<telegram_id> deep links for referrals."""
    await state.clear()
    args = message.text.split(maxsplit=1)
    ref_param = args[1] if len(args) > 1 else ""

    user, is_new = await get_or_create_user(session, message.from_user.id)

    # Process referral if new user and valid ref link
    if is_new and ref_param.startswith("ref_"):
        try:
            referrer_tg_id = int(ref_param[4:])
            referrer = await get_user_by_telegram_id(session, referrer_tg_id)
            if referrer and referrer.id != user.id:
                await create_referral(session, referrer.id, user.id)
        except (ValueError, Exception):
            pass

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


@router.message(Command("invite"))
async def cmd_invite(message: Message, session: AsyncSession) -> None:
    """Generate referral link."""
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Используйте /start для регистрации.")
        return

    count = await get_referral_count(session, user.id)
    bot_info = await message.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    await message.answer(
        f"Ваша реферальная ссылка:\n<code>{link}</code>\n\n"
        f"Приглашено друзей: <b>{count}</b>\n"
        f"Каждый друг даёт +20 к рейтингу (макс 100).",
    )
