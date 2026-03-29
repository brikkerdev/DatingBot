"""Shared utilities for bot handlers."""

from datetime import date

from aiogram.types import InputMediaPhoto, Message

from src.db.models.profile import Profile
from src.services.storage import resolve_photo


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


async def send_profile_preview(message: Message, profile: Profile) -> None:
    """Send full profile preview with all photos."""
    text = format_profile_text(profile)

    if not profile.photos:
        await message.answer(text)
        return

    if len(profile.photos) == 1:
        await message.answer_photo(
            photo=await resolve_photo(profile.photos[0].storage_path),
            caption=text,
        )
    else:
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
        await message.answer_media_group(media=media)
