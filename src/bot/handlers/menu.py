from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.reply import (
    confirm_delete_keyboard,
    main_menu_keyboard,
    profile_actions_keyboard,
)
from src.bot.utils import (
    cleanup_ui,
    replace_status,
    safe_delete_user_message,
    send_profile_preview,
)
from src.db.models.user import User
from src.services.interaction import get_match_partner_id, get_user_matches
from src.services.profile import delete_profile, get_profile_by_user_id
from src.services.ranking import recalculate_user_rating
from src.services.referral import get_referral_count
from src.services.user import get_user_by_telegram_id

router = Router()


@router.message(F.text == "Моя анкета")
async def show_my_profile(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await safe_delete_user_message(message)
    await cleanup_ui(message.bot, message.chat.id, state)

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await replace_status(message, state, "Используйте /start для регистрации.")
        return

    profile = await get_profile_by_user_id(session, user.id)
    if not profile:
        await replace_status(
            message, state, "У вас ещё нет анкеты. Используйте /start."
        )
        return

    preview_ids = await send_profile_preview(message, profile)

    rating = await recalculate_user_rating(session, user.id)
    ref_count = await get_referral_count(session, user.id)
    actions_text = (
        f"<b>Рейтинг:</b> {float(rating.combined_score):.1f}/100\n"
        f"• Анкета: {float(rating.primary_score):.0f}/100\n"
        f"• Активность: {float(rating.behavior_score):.0f}/100\n"
        f"• Рефералы: {ref_count} "
        f"(вклад {min(ref_count * 20, 100)}/100)\n\n"
        "Рейтинг влияет на то, как часто вашу анкету показывают другим.\n\n"
        "Что хотите сделать?"
    )
    actions = await message.answer(
        actions_text, reply_markup=profile_actions_keyboard()
    )
    await state.update_data(
        profile_preview_ids=preview_ids,
        profile_actions_id=actions.message_id,
    )


@router.message(F.text == "Удалить анкету")
async def confirm_delete(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await safe_delete_user_message(message)

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    profile = await get_profile_by_user_id(session, user.id)
    if not profile:
        await cleanup_ui(message.bot, message.chat.id, state)
        await replace_status(
            message, state, "У вас нет анкеты.", reply_markup=main_menu_keyboard()
        )
        return

    data = await state.get_data()
    actions_id = data.get("profile_actions_id")
    if actions_id:
        try:
            await message.bot.delete_message(message.chat.id, actions_id)
        except Exception:
            pass

    sent = await message.answer(
        "Вы уверены? Анкета и все фото будут удалены безвозвратно.",
        reply_markup=confirm_delete_keyboard(),
    )
    await state.update_data(
        profile_actions_id=None,
        profile_confirm_id=sent.message_id,
    )


@router.message(F.text == "Да, удалить анкету")
async def do_delete(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    await safe_delete_user_message(message)

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    profile = await get_profile_by_user_id(session, user.id)
    if profile:
        my_name = profile.name
        partner_tg_ids: list[int] = []
        for match in await get_user_matches(session, user.id):
            partner_id = await get_match_partner_id(match, user.id)
            partner = await session.get(User, partner_id)
            if partner:
                partner_tg_ids.append(partner.telegram_id)

        await delete_profile(session, profile.id, user_id=user.id)

        for tg_id in partner_tg_ids:
            try:
                await bot.send_message(
                    tg_id, f"<b>{my_name}</b> удалил(а) анкету. Чат закрыт."
                )
            except Exception:
                pass

    await cleanup_ui(message.bot, message.chat.id, state)
    await replace_status(
        message,
        state,
        "Анкета удалена. Используйте /start чтобы создать новую.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == "Отмена")
async def cancel_delete(message: Message, state: FSMContext) -> None:
    await safe_delete_user_message(message)

    data = await state.get_data()
    confirm_id = data.get("profile_confirm_id")
    if confirm_id:
        try:
            await message.bot.delete_message(message.chat.id, confirm_id)
        except Exception:
            pass

    sent = await message.answer(
        "Что хотите сделать?", reply_markup=profile_actions_keyboard()
    )
    await state.update_data(
        profile_confirm_id=None,
        profile_actions_id=sent.message_id,
    )


@router.message(F.text == "Назад в меню")
async def back_to_menu(message: Message, state: FSMContext) -> None:
    await safe_delete_user_message(message)
    await cleanup_ui(message.bot, message.chat.id, state)
    await replace_status(
        message, state, "Главное меню", reply_markup=main_menu_keyboard()
    )
