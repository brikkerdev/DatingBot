"""Shared utilities for bot handlers."""

from datetime import date

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InputMediaPhoto, Message

from src.db.models.profile import Profile
from src.services.storage import resolve_photo

TRACKED_UI_KEYS = (
    "browse_card_id",
    "profile_preview_ids",
    "profile_actions_id",
    "profile_confirm_id",
    "matches_list_id",
    "preview_msg_ids",
    "photo_mgr_msg_id",
    "status_msg_id",
    "reg_summary_id",
)


async def cleanup_ui(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Delete all tracked UI messages and reset their keys."""
    data = await state.get_data()
    for key in TRACKED_UI_KEYS:
        val = data.get(key)
        if not val:
            continue
        ids = val if isinstance(val, list) else [val]
        for mid in ids:
            try:
                await bot.delete_message(chat_id, mid)
            except Exception:
                pass
    await state.update_data(**{k: None for k in TRACKED_UI_KEYS})


async def replace_status(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup=None,
) -> None:
    """Send a single-instance status message; delete the previous one if present."""
    data = await state.get_data()
    prev = data.get("status_msg_id")
    if prev:
        try:
            await message.bot.delete_message(message.chat.id, prev)
        except Exception:
            pass
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(status_msg_id=sent.message_id)


def format_profile_text(profile: Profile) -> str:
    gender = "Мужской" if profile.gender == "male" else "Женский"
    bio = profile.bio or "—"
    age = (date.today() - profile.birth_date).days // 365
    return (
        f"<b>{profile.name}</b>, {age}\n"
        f"Город: {profile.city}\n"
        f"Пол: {gender}\n"
        f"О себе: {bio}"
    )


async def send_profile_preview(message: Message, profile: Profile) -> list[int]:
    """Send full profile preview with all photos. Returns sent message ids."""
    text = format_profile_text(profile)

    if not profile.photos:
        sent = await message.answer(text)
        return [sent.message_id]

    if len(profile.photos) == 1:
        sent = await message.answer_photo(
            photo=await resolve_photo(profile.photos[0].storage_path),
            caption=text,
        )
        return [sent.message_id]

    media = []
    for i, photo in enumerate(profile.photos):
        resolved = await resolve_photo(photo.storage_path)
        media.append(
            InputMediaPhoto(
                media=resolved,
                caption=text if i == 0 else None,
                parse_mode="HTML" if i == 0 else None,
            )
        )
    msgs = await message.answer_media_group(media=media)
    return [m.message_id for m in msgs]
