from datetime import date

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.reply import main_menu_keyboard
from src.services.profile import get_profile_by_user_id
from src.services.user import get_user_by_telegram_id

router = Router()


@router.message(F.text == "Моя анкета")
async def show_my_profile(message: Message, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Используйте /start для регистрации.")
        return

    profile = await get_profile_by_user_id(session, user.id)
    if not profile:
        await message.answer("У вас ещё нет анкеты. Используйте /start.")
        return

    gender_display = "Мужской" if profile.gender == "male" else "Женский"
    bio_display = profile.bio or "—"
    age = (date.today() - profile.birth_date).days // 365

    text = (
        f"<b>{profile.name}</b>, {age}\n"
        f"Город: {profile.city}\n"
        f"Пол: {gender_display}\n"
        f"О себе: {bio_display}"
    )

    if profile.photos:
        await message.answer_photo(
            photo=profile.photos[0].storage_path,
            caption=text,
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(text, reply_markup=main_menu_keyboard())
