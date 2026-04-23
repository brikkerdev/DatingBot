import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import (
    cancel_add_photo_inline,
    edit_profile_keyboard,
    gender_inline,
    main_menu_inline,
    photo_manage_keyboard,
    skip_bio_inline,
)
from src.bot.keyboards.reply import remove_keyboard
from src.bot.states.registration import EditProfileState
from src.services.profile import (
    add_photo,
    delete_photo,
    get_profile_by_user_id,
    swap_photo_order,
    update_profile,
)
from src.services.storage import ensure_bucket, resolve_photo, upload_photo
from src.services.user import get_user_by_telegram_id
from src.bot.utils import (
    cleanup_ui,
    format_profile_text,
    send_profile_preview,
)

logger = logging.getLogger(__name__)

router = Router()

MAX_PHOTOS = 6


# --- Helpers ---


async def _get_fresh_profile(session: AsyncSession, user_id: int):
    """Expire cache and get fresh profile with photos."""
    session.expire_all()
    return await get_profile_by_user_id(session, user_id)


async def _replace_edit_menu(message: Message, state: FSMContext, text: str) -> None:
    """Delete the previous edit menu, send a new one, and track it."""
    data = await state.get_data()
    prev = data.get("profile_actions_id")
    if prev:
        try:
            await message.bot.delete_message(message.chat.id, prev)
        except Exception:
            pass
    sent = await message.answer(text, reply_markup=edit_profile_keyboard())
    await state.update_data(profile_actions_id=sent.message_id)


async def _delete_old_preview(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Delete previously sent preview and manager messages."""
    data = await state.get_data()
    for msg_id in data.get("preview_msg_ids", []):
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    mgr_id = data.get("photo_mgr_msg_id")
    if mgr_id:
        try:
            await bot.delete_message(chat_id, mgr_id)
        except Exception:
            pass
    await state.update_data(preview_msg_ids=[], photo_mgr_msg_id=None)


async def _send_photo_editor(
    session: AsyncSession,
    user_id: int,
    *,
    bot: Bot,
    chat_id: int,
    state: FSMContext,
) -> None:
    """Send full photo editor: preview of profile + management keyboard."""
    # Clean up old messages
    await _delete_old_preview(bot, chat_id, state)

    profile = await _get_fresh_profile(session, user_id)
    if not profile:
        return

    # Send profile preview and track message ids
    preview_ids: list[int] = []
    if profile.photos:
        if len(profile.photos) == 1:
            msg = await bot.send_photo(
                chat_id,
                photo=await resolve_photo(profile.photos[0].storage_path),
                caption=format_profile_text(profile),
            )
            preview_ids.append(msg.message_id)
        else:
            from aiogram.types import InputMediaPhoto

            media = []
            text = format_profile_text(profile)
            for i, photo in enumerate(profile.photos):
                resolved = await resolve_photo(photo.storage_path)
                media.append(
                    InputMediaPhoto(
                        media=resolved,
                        caption=text if i == 0 else None,
                        parse_mode="HTML" if i == 0 else None,
                    )
                )
            msgs = await bot.send_media_group(chat_id, media=media)
            preview_ids.extend(m.message_id for m in msgs)
    else:
        msg = await bot.send_message(chat_id, format_profile_text(profile))
        preview_ids.append(msg.message_id)

    # Send management keyboard
    photos = [(p.id, p.sort_order) for p in profile.photos]
    count = len(photos)
    text = f"<b>Ваши фото ({count}/{MAX_PHOTOS}):</b>\n"
    text += (
        "Используйте кнопки для управления."
        if count
        else "Нет фото. Добавьте хотя бы одно."
    )

    kb = photo_manage_keyboard(photos, MAX_PHOTOS)
    sent = await bot.send_message(chat_id, text, reply_markup=kb)

    await state.update_data(
        preview_msg_ids=preview_ids, photo_mgr_msg_id=sent.message_id
    )


# --- Entry point ---


@router.callback_query(F.data == "prof:edit")
async def start_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await callback.answer()
    await cleanup_ui(callback.message.bot, callback.message.chat.id, state)

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.message.answer("Используйте /start для регистрации.")
        return

    profile = await get_profile_by_user_id(session, user.id)
    if not profile:
        await callback.message.answer("У вас ещё нет анкеты. Используйте /start.")
        return

    preview_ids = await send_profile_preview(callback.message, profile)

    await state.set_state(EditProfileState.choosing_field)
    sent = await callback.message.answer(
        "Что хотите изменить?", reply_markup=edit_profile_keyboard()
    )
    await state.update_data(
        user_id=user.id,
        profile_preview_ids=preview_ids,
        profile_actions_id=sent.message_id,
    )


# --- Field selection callbacks ---


@router.callback_query(EditProfileState.choosing_field, F.data == "edit:name")
async def edit_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileState.editing_name)
    await callback.answer()
    await callback.message.answer("Введите новое имя:", reply_markup=remove_keyboard)


@router.callback_query(EditProfileState.choosing_field, F.data == "edit:age")
async def edit_age_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileState.editing_age)
    await callback.answer()
    await callback.message.answer(
        "Введите новый возраст:", reply_markup=remove_keyboard
    )


@router.callback_query(EditProfileState.choosing_field, F.data == "edit:gender")
async def edit_gender_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileState.editing_gender)
    await callback.answer()
    await callback.message.answer("Выберите пол:", reply_markup=gender_inline())


@router.callback_query(EditProfileState.choosing_field, F.data == "edit:city")
async def edit_city_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileState.editing_city)
    await callback.answer()
    await callback.message.answer("Введите новый город:", reply_markup=remove_keyboard)


@router.callback_query(EditProfileState.choosing_field, F.data == "edit:bio")
async def edit_bio_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditProfileState.editing_bio)
    await callback.answer()
    await callback.message.answer(
        "Введите новое описание (до 500 символов) или нажмите кнопку, чтобы убрать:",
        reply_markup=skip_bio_inline(),
    )


@router.callback_query(EditProfileState.choosing_field, F.data == "edit:photo")
async def edit_photo_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    data = await state.get_data()
    user_id = data["user_id"]
    await cleanup_ui(bot, callback.message.chat.id, state)
    await state.set_state(EditProfileState.editing_photo)
    await state.update_data(
        user_id=user_id, preview_msg_ids=[], photo_mgr_msg_id=None
    )
    await callback.answer()
    await _send_photo_editor(
        session,
        user_id,
        bot=bot,
        chat_id=callback.message.chat.id,
        state=state,
    )


@router.callback_query(EditProfileState.choosing_field, F.data == "edit:cancel")
async def edit_cancel(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    await cleanup_ui(bot, callback.message.chat.id, state)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await state.clear()
    await callback.answer()
    await callback.message.answer("Главное меню", reply_markup=main_menu_inline())


# --- Text field editors ---


@router.message(EditProfileState.editing_name, F.text)
async def edit_name_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    name = message.text.strip()
    if not name or len(name) > 100:
        await message.answer("Имя от 1 до 100 символов:")
        return

    data = await state.get_data()
    profile = await get_profile_by_user_id(session, data["user_id"])
    await update_profile(session, profile, name=name)

    await state.set_state(EditProfileState.choosing_field)
    await _replace_edit_menu(
        message, state, f"Имя изменено на <b>{name}</b>.\n\nЧто ещё изменить?"
    )


@router.message(EditProfileState.editing_age, F.text)
async def edit_age_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    try:
        age = int(message.text.strip())
    except ValueError:
        await message.answer("Введите возраст числом:")
        return

    if age < 18:
        await message.answer("Минимум 18 лет.")
        return
    if age > 100:
        await message.answer("Введите корректный возраст:")
        return

    today = date.today()
    birth_date = date(today.year - age, today.month, today.day)

    data = await state.get_data()
    profile = await get_profile_by_user_id(session, data["user_id"])
    await update_profile(session, profile, birth_date=birth_date)

    await state.set_state(EditProfileState.choosing_field)
    await _replace_edit_menu(
        message, state, f"Возраст изменён на <b>{age}</b>.\n\nЧто ещё изменить?"
    )


@router.callback_query(EditProfileState.editing_gender, F.data.startswith("gender:"))
async def edit_gender_save(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    gender = callback.data.split(":")[1]
    gender_text = "Мужской" if gender == "male" else "Женский"

    data = await state.get_data()
    profile = await get_profile_by_user_id(session, data["user_id"])
    await update_profile(session, profile, gender=gender)

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.set_state(EditProfileState.choosing_field)
    await _replace_edit_menu(
        callback.message,
        state,
        f"Пол изменён на <b>{gender_text}</b>.\n\nЧто ещё изменить?",
    )


@router.message(EditProfileState.editing_city, F.text)
async def edit_city_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    city = message.text.strip()
    if not city or len(city) > 100:
        await message.answer("Город от 1 до 100 символов:")
        return

    data = await state.get_data()
    profile = await get_profile_by_user_id(session, data["user_id"])
    await update_profile(session, profile, city=city)

    await state.set_state(EditProfileState.choosing_field)
    await _replace_edit_menu(
        message, state, f"Город изменён на <b>{city}</b>.\n\nЧто ещё изменить?"
    )


@router.message(EditProfileState.editing_bio, F.text)
async def edit_bio_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    bio = message.text.strip()
    if len(bio) > 500:
        await message.answer("Максимум 500 символов:")
        return

    data = await state.get_data()
    profile = await get_profile_by_user_id(session, data["user_id"])
    await update_profile(session, profile, bio=bio)

    await state.set_state(EditProfileState.choosing_field)
    await _replace_edit_menu(
        message,
        state,
        f"Описание обновлено: <b>{bio}</b>.\n\nЧто ещё изменить?",
    )


@router.callback_query(EditProfileState.editing_bio, F.data == "bio:skip")
async def edit_bio_skip(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    profile = await get_profile_by_user_id(session, data["user_id"])
    await update_profile(session, profile, bio=None)

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.set_state(EditProfileState.choosing_field)
    await _replace_edit_menu(
        callback.message, state, "Описание убрано.\n\nЧто ещё изменить?"
    )


# --- Photo management ---


@router.callback_query(EditProfileState.editing_photo, F.data == "ph_noop")
async def photo_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(EditProfileState.editing_photo, F.data.startswith("ph_del:"))
async def photo_delete(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    photo_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    profile = await _get_fresh_profile(session, data["user_id"])
    if profile and len(profile.photos) <= 1:
        await callback.answer("Нельзя удалить последнее фото!")
        return

    await delete_photo(session, photo_id)
    await callback.answer("Фото удалено")
    await _send_photo_editor(
        session,
        data["user_id"],
        bot=bot,
        chat_id=callback.message.chat.id,
        state=state,
    )


@router.callback_query(EditProfileState.editing_photo, F.data.startswith("ph_up:"))
async def photo_move_up(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    photo_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    profile = await _get_fresh_profile(session, data["user_id"])
    if not profile:
        await callback.answer()
        return

    photos = sorted(profile.photos, key=lambda p: p.sort_order)
    for i, p in enumerate(photos):
        if p.id == photo_id and i > 0:
            await swap_photo_order(session, photos[i].id, photos[i - 1].id)
            break

    await callback.answer("Перемещено")
    await _send_photo_editor(
        session,
        data["user_id"],
        bot=bot,
        chat_id=callback.message.chat.id,
        state=state,
    )


@router.callback_query(EditProfileState.editing_photo, F.data.startswith("ph_down:"))
async def photo_move_down(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    photo_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    profile = await _get_fresh_profile(session, data["user_id"])
    if not profile:
        await callback.answer()
        return

    photos = sorted(profile.photos, key=lambda p: p.sort_order)
    for i, p in enumerate(photos):
        if p.id == photo_id and i < len(photos) - 1:
            await swap_photo_order(session, photos[i].id, photos[i + 1].id)
            break

    await callback.answer("Перемещено")
    await _send_photo_editor(
        session,
        data["user_id"],
        bot=bot,
        chat_id=callback.message.chat.id,
        state=state,
    )


@router.callback_query(EditProfileState.editing_photo, F.data == "ph_add")
async def photo_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    sent = await callback.message.answer(
        "Отправьте фото:", reply_markup=cancel_add_photo_inline()
    )
    await state.update_data(ph_add_prompt_id=sent.message_id)


@router.callback_query(EditProfileState.editing_photo, F.data == "ph_cancel_add")
async def photo_add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await state.update_data(ph_add_prompt_id=None)


@router.message(EditProfileState.editing_photo, F.photo)
async def photo_add_receive(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    data = await state.get_data()
    prompt_id = data.get("ph_add_prompt_id")
    if prompt_id:
        try:
            await bot.delete_message(message.chat.id, prompt_id)
        except Exception:
            pass
        await state.update_data(ph_add_prompt_id=None)

    profile = await _get_fresh_profile(session, data["user_id"])
    if not profile:
        return

    if len(profile.photos) >= MAX_PHOTOS:
        await message.answer(f"Максимум {MAX_PHOTOS} фото.")
        return

    file_id = message.photo[-1].file_id
    next_order = max((p.sort_order for p in profile.photos), default=-1) + 1

    try:
        await ensure_bucket()
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        s3_key = await upload_photo(file_bytes.read())
        await add_photo(session, profile.id, storage_path=s3_key, sort_order=next_order)
    except Exception:
        logger.warning("S3 upload failed, falling back to file_id")
        await add_photo(
            session, profile.id, storage_path=file_id, sort_order=next_order
        )

    await session.commit()

    # Update the existing management message in-place
    await _send_photo_editor(
        session,
        data["user_id"],
        bot=bot,
        chat_id=message.chat.id,
        state=state,
    )


@router.callback_query(EditProfileState.editing_photo, F.data == "ph_done")
async def photo_done(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _delete_old_preview(bot, callback.message.chat.id, state)
    await state.set_state(EditProfileState.choosing_field)
    await callback.answer()
    await _replace_edit_menu(callback.message, state, "Что ещё изменить?")


@router.message(EditProfileState.editing_photo)
async def photo_invalid(message: Message) -> None:
    await message.answer("Отправьте фото или используйте кнопки выше.")
