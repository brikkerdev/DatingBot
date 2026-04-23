import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.inline import (
    confirm_registration_inline,
    gender_inline,
    main_menu_inline,
    photo_done_inline,
    skip_bio_inline,
)
from src.bot.states.registration import RegistrationState
from src.bot.utils import replace_status
from src.services.profile import add_photo, create_profile
from src.services.storage import ensure_bucket, upload_photo

logger = logging.getLogger(__name__)

router = Router()

MAX_PHOTOS = 6


# --- Name ---


@router.message(RegistrationState.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name or len(name) > 100:
        await message.answer(
            "Имя должно быть от 1 до 100 символов. Попробуйте ещё раз:"
        )
        return

    await state.update_data(name=name)
    await state.set_state(RegistrationState.waiting_for_age)
    await message.answer("Сколько вам лет?")


# --- Age ---


@router.message(RegistrationState.waiting_for_age, F.text)
async def process_age(message: Message, state: FSMContext) -> None:
    try:
        age = int(message.text.strip())
    except ValueError:
        await message.answer("Введите возраст числом:")
        return

    if age < 18:
        await message.answer("Вам должно быть не менее 18 лет.")
        return
    if age > 100:
        await message.answer("Введите корректный возраст:")
        return

    today = date.today()
    birth_date = date(today.year - age, today.month, today.day)

    await state.update_data(age=age, birth_date=birth_date.isoformat())
    await state.set_state(RegistrationState.waiting_for_gender)
    await message.answer("Укажите ваш пол:", reply_markup=gender_inline())


# --- Gender ---


@router.callback_query(
    RegistrationState.waiting_for_gender, F.data.startswith("gender:")
)
async def process_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":")[1]
    gender_text = "Мужской" if gender == "male" else "Женский"
    await state.update_data(gender=gender)
    await state.set_state(RegistrationState.waiting_for_city)

    await callback.answer()
    try:
        await callback.message.edit_text(f"Пол: <b>{gender_text}</b>")
    except Exception:
        pass
    await callback.message.answer("В каком вы городе?")


# --- City ---


@router.message(RegistrationState.waiting_for_city, F.text)
async def process_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    if not city or len(city) > 100:
        await message.answer("Название города — от 1 до 100 символов:")
        return

    await state.update_data(city=city)
    await state.set_state(RegistrationState.waiting_for_bio)
    await message.answer(
        "Расскажите о себе (до 500 символов) или нажмите кнопку, чтобы пропустить.",
        reply_markup=skip_bio_inline(),
    )


# --- Bio ---


async def _advance_to_photos(message: Message, state: FSMContext) -> None:
    await state.update_data(photos=[])
    await state.set_state(RegistrationState.waiting_for_photo)
    await message.answer("Отправьте хотя бы 1 фото (максимум 6).")


@router.message(RegistrationState.waiting_for_bio, F.text)
async def process_bio(message: Message, state: FSMContext) -> None:
    bio = message.text.strip()
    if len(bio) > 500:
        await message.answer(
            "Описание не должно превышать 500 символов. Попробуйте короче:"
        )
        return
    await state.update_data(bio=bio)
    await _advance_to_photos(message, state)


@router.callback_query(RegistrationState.waiting_for_bio, F.data == "bio:skip")
async def process_bio_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(bio=None)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _advance_to_photos(callback.message, state)


# --- Photos ---


@router.message(RegistrationState.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])

    if len(photos) >= MAX_PHOTOS:
        await message.answer(f'Максимум {MAX_PHOTOS} фото. Нажмите "Готово".')
        return

    # Download from Telegram and upload to S3 (Minio)
    file_id = message.photo[-1].file_id
    try:
        await ensure_bucket()
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        s3_key = await upload_photo(file_bytes.read())
        photos.append(s3_key)
    except Exception:
        logger.warning("S3 upload failed, falling back to file_id")
        photos.append(file_id)

    await state.update_data(photos=photos)
    await message.answer(
        f"Фото добавлено ({len(photos)}/{MAX_PHOTOS}). Когда закончите — нажмите кнопку.",
        reply_markup=photo_done_inline(),
    )


@router.callback_query(
    RegistrationState.waiting_for_photo, F.data == "reg:photos_done"
)
async def process_photo_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])

    if not photos:
        await callback.answer("Нужно загрузить хотя бы 1 фото", show_alert=True)
        return

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.set_state(RegistrationState.confirm)

    gender_display = "Мужской" if data["gender"] == "male" else "Женский"
    bio_display = data.get("bio") or "—"

    summary = (
        "<b>Ваша анкета:</b>\n\n"
        f"<b>Имя:</b> {data['name']}\n"
        f"<b>Возраст:</b> {data['age']}\n"
        f"<b>Пол:</b> {gender_display}\n"
        f"<b>Город:</b> {data['city']}\n"
        f"<b>О себе:</b> {bio_display}\n"
        f"<b>Фото:</b> {len(photos)} шт.\n\n"
        "Всё верно?"
    )
    sent = await callback.message.answer(
        summary, reply_markup=confirm_registration_inline()
    )
    await state.update_data(reg_summary_id=sent.message_id)


@router.message(RegistrationState.waiting_for_photo)
async def process_photo_invalid(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[str] = data.get("photos", [])
    if photos:
        await message.answer(
            "Отправьте фото или нажмите кнопку ниже.",
            reply_markup=photo_done_inline(),
        )
    else:
        await message.answer("Отправьте фото.")


# --- Confirm ---


@router.callback_query(RegistrationState.confirm, F.data == "reg:save")
async def process_confirm_save(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await callback.answer()
    data = await state.get_data()

    summary_id = data.get("reg_summary_id")
    if summary_id:
        try:
            await callback.message.bot.delete_message(
                callback.message.chat.id, summary_id
            )
        except Exception:
            pass

    profile = await create_profile(
        session,
        user_id=data["user_id"],
        name=data["name"],
        birth_date=date.fromisoformat(data["birth_date"]),
        gender=data["gender"],
        city=data["city"],
        bio=data.get("bio"),
    )

    for i, file_id in enumerate(data["photos"]):
        await add_photo(session, profile.id, storage_path=file_id, sort_order=i)

    await session.commit()
    await state.clear()

    await replace_status(
        callback.message,
        state,
        f"Анкета создана, {data['name']}! Добро пожаловать!",
        reply_markup=main_menu_inline(),
    )


@router.callback_query(RegistrationState.confirm, F.data == "reg:restart")
async def process_confirm_restart(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await callback.answer()
    data = await state.get_data()
    user_id = data["user_id"]

    summary_id = data.get("reg_summary_id")
    if summary_id:
        try:
            await callback.message.bot.delete_message(
                callback.message.chat.id, summary_id
            )
        except Exception:
            pass

    await state.clear()
    await state.update_data(user_id=user_id)
    await state.set_state(RegistrationState.waiting_for_name)
    await callback.message.answer("Начнём заново. Как вас зовут?")
