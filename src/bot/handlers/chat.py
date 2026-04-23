import json

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import main_menu_inline
from src.bot.states.chat import ChatState
from src.bot.utils import cleanup_ui
from src.db.models.user import User
from src.services.chat import (
    count_unread_from_sender,
    get_match_by_id,
    get_messages,
    is_user_in_match,
    mark_match_read,
    send_message,
)
from src.services.profile import get_profile_by_user_id
from src.services.user import get_user_by_telegram_id

router = Router()


def chat_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Выйти из чата")]],
        resize_keyboard=True,
    )


async def _partner_active_in_match(
    redis: Redis, partner_tg_id: int, match_id: int
) -> bool:
    """Check partner's FSM state in Redis to see if they're currently in this chat."""
    state = await redis.get(f"fsm:{partner_tg_id}:{partner_tg_id}:state")
    if state != "ChatState:in_chat":
        return False
    data_raw = await redis.get(f"fsm:{partner_tg_id}:{partner_tg_id}:data")
    if not data_raw:
        return False
    try:
        data = json.loads(data_raw)
    except (ValueError, TypeError):
        return False
    return data.get("match_id") == match_id


@router.callback_query(F.data.startswith("chat:"))
async def enter_chat(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    match_id = int(callback.data.split(":")[1])

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    await cleanup_ui(callback.message.bot, callback.message.chat.id, state)

    match = await get_match_by_id(session, match_id)
    if not match or not await is_user_in_match(match, user.id):
        await callback.answer("Мэтч не найден")
        return

    partner_id = match.user2_id if match.user1_id == user.id else match.user1_id
    partner_profile = await get_profile_by_user_id(session, partner_id)
    partner_name = partner_profile.name if partner_profile else "Собеседник"
    partner_user = await session.get(User, partner_id)
    partner_tg_id = partner_user.telegram_id if partner_user else 0

    await mark_match_read(session, match_id, user.id)

    await state.set_state(ChatState.in_chat)
    await state.update_data(
        match_id=match_id,
        partner_telegram_id=partner_tg_id,
        partner_name=partner_name,
    )

    messages = await get_messages(session, match_id, limit=20)
    if messages:
        lines = []
        for msg in messages:
            sender = "Вы" if msg.from_user_id == user.id else partner_name
            lines.append(f"<b>{sender}:</b> {msg.content}")
        history = "\n".join(lines)
    else:
        history = "<i>Сообщений пока нет. Напишите первым!</i>"

    await callback.answer()
    await callback.message.answer(
        f"Чат с <b>{partner_name}</b>\n\n{history}",
        reply_markup=chat_keyboard(),
    )


@router.message(ChatState.in_chat, F.text == "Выйти из чата")
async def exit_chat(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Вы вышли из чата.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Главное меню", reply_markup=main_menu_inline())


@router.message(ChatState.in_chat, F.text)
async def chat_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    data = await state.get_data()
    match_id = data["match_id"]
    partner_tg_id = data["partner_telegram_id"]

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    my_profile = await get_profile_by_user_id(session, user.id)
    my_name = my_profile.name if my_profile else "Собеседник"

    partner_active = await _partner_active_in_match(redis, partner_tg_id, match_id)

    await send_message(
        session, match_id, user.id, message.text, mark_read=partner_active
    )

    if partner_active:
        try:
            await bot.send_message(
                partner_tg_id, f"<b>{my_name}:</b> {message.text}"
            )
        except Exception:
            pass
        return

    unread_count = await count_unread_from_sender(session, match_id, user.id)
    if unread_count == 1:
        try:
            await bot.send_message(
                partner_tg_id,
                f"У вас непрочитанное сообщение от <b>{my_name}</b>.\n"
                "Загляните в «Мэтчи», чтобы прочитать.",
            )
        except Exception:
            pass
