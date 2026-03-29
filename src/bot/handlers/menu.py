from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.reply import (
    confirm_delete_keyboard,
    main_menu_keyboard,
    profile_actions_keyboard,
)
from src.bot.utils import send_profile_preview
from src.services.profile import delete_profile, get_profile_by_user_id
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

    await send_profile_preview(message, profile)
    await message.answer("Что хотите сделать?", reply_markup=profile_actions_keyboard())


@router.message(F.text == "Удалить анкету")
async def confirm_delete(message: Message, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    profile = await get_profile_by_user_id(session, user.id)
    if not profile:
        await message.answer("У вас нет анкеты.", reply_markup=main_menu_keyboard())
        return

    await message.answer(
        "Вы уверены? Анкета и все фото будут удалены безвозвратно.",
        reply_markup=confirm_delete_keyboard(),
    )


@router.message(F.text == "Да, удалить анкету")
async def do_delete(message: Message, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    profile = await get_profile_by_user_id(session, user.id)
    if not profile:
        await message.answer("Анкета уже удалена.", reply_markup=main_menu_keyboard())
        return

    await delete_profile(session, profile.id, user_id=user.id)
    await message.answer(
        "Анкета удалена. Используйте /start чтобы создать новую.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == "Отмена")
async def cancel_delete(message: Message) -> None:
    await message.answer("Удаление отменено.", reply_markup=main_menu_keyboard())


@router.message(F.text == "Назад в меню")
async def back_to_menu(message: Message) -> None:
    await message.answer("Главное меню", reply_markup=main_menu_keyboard())
