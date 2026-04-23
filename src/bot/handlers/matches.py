from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import main_menu_inline, match_list_keyboard
from src.bot.utils import cleanup_ui, replace_status
from src.services.chat import get_unread_match_ids
from src.services.interaction import get_match_partner_id, get_user_matches
from src.services.profile import get_profile_by_user_id
from src.services.user import get_user_by_telegram_id

router = Router()


@router.callback_query(F.data == "menu:matches")
async def show_matches(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await callback.answer()
    await cleanup_ui(callback.message.bot, callback.message.chat.id, state)

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await replace_status(
            callback.message, state, "Используйте /start для регистрации."
        )
        return

    matches = await get_user_matches(session, user.id)
    if not matches:
        await replace_status(
            callback.message,
            state,
            "У вас пока нет мэтчей. Ставьте лайки!",
            reply_markup=main_menu_inline(),
        )
        return

    unread = await get_unread_match_ids(session, user.id)

    items: list[tuple[int, str]] = []
    for match in matches:
        partner_id = await get_match_partner_id(match, user.id)
        partner_profile = await get_profile_by_user_id(session, partner_id)
        name = (
            partner_profile.name if partner_profile else f"Пользователь #{partner_id}"
        )
        if match.id in unread:
            name = f"🔴 {name}"
        items.append((match.id, name))

    header = "<b>Ваши мэтчи:</b>\nНажмите на имя, чтобы начать чат."
    if unread:
        header += f"\n🔴 — новые сообщения ({len(unread)})."

    sent = await callback.message.answer(
        header,
        reply_markup=match_list_keyboard(items),
    )
    await state.update_data(matches_list_id=sent.message_id)
