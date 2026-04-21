from datetime import date

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import like_pass_keyboard
from src.bot.keyboards.reply import main_menu_keyboard
from src.db.models.profile import Profile
from src.services.interaction import get_next_profiles, record_like, record_pass
from src.services.profile import get_profile_by_user_id
from src.services.profile_queue import fill_queue, pop_profile, queue_length
from src.services.storage import resolve_photo
from src.services.user import get_user_by_telegram_id

router = Router()


def _format_card(profile: Profile) -> str:
    age = (date.today() - profile.birth_date).days // 365
    gender = "Мужской" if profile.gender == "male" else "Женский"
    bio = profile.bio or "—"
    return (
        f"<b>{profile.name}</b>, {age}\n"
        f"Город: {profile.city}\n"
        f"Пол: {gender}\n"
        f"О себе: {bio}"
    )


def _format_card_from_dict(d: dict) -> str:
    age = (date.today() - date.fromisoformat(d["birth_date"])).days // 365
    gender = "Мужской" if d["gender"] == "male" else "Женский"
    bio = d.get("bio") or "—"
    return (
        f"<b>{d['name']}</b>, {age}\n"
        f"Город: {d.get('city', '')}\n"
        f"Пол: {gender}\n"
        f"О себе: {bio}"
    )


async def _send_card(
    message: Message, text: str, photo: str, target_user_id: int
) -> None:
    keyboard = like_pass_keyboard(target_user_id)
    if photo:
        await message.answer_photo(
            photo=await resolve_photo(photo), caption=text, reply_markup=keyboard
        )
    else:
        await message.answer(text, reply_markup=keyboard)


async def _show_next(
    message: Message, session: AsyncSession, redis: Redis, user_id: int
) -> None:
    """Show next profile — from Redis queue, or refill from DB."""
    # Try Redis cache first
    cached = await pop_profile(redis, user_id)
    if cached:
        text = _format_card_from_dict(cached)
        await _send_card(message, text, cached.get("photo", ""), cached["user_id"])

        # If queue is now empty, refill — exclude the just-shown profile since
        # the like/pass hasn't been recorded yet and it would come back on top.
        if await queue_length(redis, user_id) == 0:
            await fill_queue(
                redis, session, user_id, exclude_user_ids={cached["user_id"]}
            )
        return

    # Cache empty — load from DB (first call or cache expired)
    profiles = await get_next_profiles(session, user_id, limit=1)
    if not profiles:
        await message.answer(
            "Анкеты закончились. Загляните позже!", reply_markup=main_menu_keyboard()
        )
        return

    profile = profiles[0]
    text = _format_card(profile)
    photo = profile.photos[0].storage_path if profile.photos else ""
    await _send_card(message, text, photo, profile.user_id)

    # Pre-fill queue with next batch, excluding the profile we just showed so
    # it doesn't get served again before the user acts on it.
    await fill_queue(redis, session, user_id, exclude_user_ids={profile.user_id})


@router.message(F.text == "Смотреть анкеты")
async def browse_profiles(
    message: Message, session: AsyncSession, redis: Redis
) -> None:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Используйте /start для регистрации.")
        return

    profile = await get_profile_by_user_id(session, user.id)
    if not profile:
        await message.answer("Сначала создайте анкету через /start.")
        return

    await _show_next(message, session, redis, user.id)


@router.callback_query(F.data.startswith("like:"))
async def process_like(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    redis: Redis,
) -> None:
    target_user_id = int(callback.data.split(":")[1])

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    match = await record_like(session, user.id, target_user_id)

    if match:
        partner_profile = await get_profile_by_user_id(session, target_user_id)
        partner_name = partner_profile.name if partner_profile else "Кто-то"
        await callback.answer("Взаимный лайк!")
        await callback.message.answer(
            f"<b>Мэтч!</b> Вы понравились <b>{partner_name}</b>!\n"
            f"Загляните в «Мэтчи», чтобы начать общение.",
            reply_markup=main_menu_keyboard(),
        )
        # Partner notification is handled by the notification consumer via MQ
    else:
        await callback.answer("Like!")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _show_next(callback.message, session, redis, user.id)


@router.callback_query(F.data.startswith("pass:"))
async def process_pass(
    callback: CallbackQuery, session: AsyncSession, redis: Redis
) -> None:
    target_user_id = int(callback.data.split(":")[1])

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    await record_pass(session, user.id, target_user_id)
    await callback.answer("Skip")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _show_next(callback.message, session, redis, user.id)
