from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import match_list_keyboard
from src.bot.keyboards.reply import main_menu_keyboard
from src.services.interaction import get_match_partner_id, get_user_matches
from src.services.profile import get_profile_by_user_id
from src.services.user import get_user_by_telegram_id

router = Router()


@router.message(F.text == "Мэтчи")
async def show_matches(message: Message, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Используйте /start для регистрации.")
        return

    matches = await get_user_matches(session, user.id)
    if not matches:
        await message.answer(
            "У вас пока нет мэтчей. Ставьте лайки!",
            reply_markup=main_menu_keyboard(),
        )
        return

    items: list[tuple[int, str]] = []
    for match in matches:
        partner_id = await get_match_partner_id(match, user.id)
        partner_profile = await get_profile_by_user_id(session, partner_id)
        name = (
            partner_profile.name if partner_profile else f"Пользователь #{partner_id}"
        )
        items.append((match.id, name))

    await message.answer(
        "<b>Ваши мэтчи:</b>\nНажмите на имя, чтобы начать чат.",
        reply_markup=match_list_keyboard(items),
    )
