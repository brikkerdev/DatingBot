from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Смотреть анкеты", callback_data="menu:browse")],
            [
                InlineKeyboardButton(text="Моя анкета", callback_data="menu:profile"),
                InlineKeyboardButton(text="Мэтчи", callback_data="menu:matches"),
            ],
            [InlineKeyboardButton(text="Пригласить друга", callback_data="menu:invite")],
        ]
    )


def profile_actions_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Редактировать анкету", callback_data="prof:edit")],
            [
                InlineKeyboardButton(text="Удалить анкету", callback_data="prof:delete"),
                InlineKeyboardButton(text="Назад в меню", callback_data="prof:back"),
            ],
        ]
    )


def confirm_delete_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data="del:yes"),
                InlineKeyboardButton(text="Отмена", callback_data="del:no"),
            ],
        ]
    )


def gender_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Мужской", callback_data="gender:male"),
                InlineKeyboardButton(text="Женский", callback_data="gender:female"),
            ],
        ]
    )


def skip_bio_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data="bio:skip")],
        ]
    )


def photo_done_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Готово", callback_data="reg:photos_done")],
        ]
    )


def confirm_registration_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сохранить", callback_data="reg:save"),
                InlineKeyboardButton(text="Заново", callback_data="reg:restart"),
            ],
        ]
    )


def like_pass_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️", callback_data=f"like:{target_user_id}"),
                InlineKeyboardButton(text="👎", callback_data=f"pass:{target_user_id}"),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню", callback_data="browse_stop"
                ),
            ],
        ]
    )


def match_list_keyboard(matches: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """matches: list of (match_id, partner_name)."""
    keyboard = [
        [InlineKeyboardButton(text=name, callback_data=f"chat:{match_id}")]
        for match_id, name in matches
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def edit_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Имя", callback_data="edit:name"),
                InlineKeyboardButton(text="Возраст", callback_data="edit:age"),
            ],
            [
                InlineKeyboardButton(text="Пол", callback_data="edit:gender"),
                InlineKeyboardButton(text="Город", callback_data="edit:city"),
            ],
            [
                InlineKeyboardButton(text="О себе", callback_data="edit:bio"),
                InlineKeyboardButton(text="Фото", callback_data="edit:photo"),
            ],
            [InlineKeyboardButton(text="Назад", callback_data="edit:cancel")],
        ]
    )


def cancel_add_photo_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Готово", callback_data="ph_cancel_add")],
        ]
    )


def photo_manage_keyboard(
    photos: list[tuple[int, int]],  # (photo_id, sort_order)
    max_photos: int = 6,
) -> InlineKeyboardMarkup:
    """Build keyboard for managing individual photos.

    Each photo row: [Move Up] [#N] [Move Down] [Delete]
    Bottom: [Add photo] [Done]
    """
    rows: list[list[InlineKeyboardButton]] = []
    for i, (photo_id, _) in enumerate(photos):
        row = []
        if i > 0:
            row.append(
                InlineKeyboardButton(text="^", callback_data=f"ph_up:{photo_id}")
            )
        else:
            row.append(InlineKeyboardButton(text=" ", callback_data="ph_noop"))
        row.append(InlineKeyboardButton(text=f"Фото {i + 1}", callback_data="ph_noop"))
        if i < len(photos) - 1:
            row.append(
                InlineKeyboardButton(text="v", callback_data=f"ph_down:{photo_id}")
            )
        else:
            row.append(InlineKeyboardButton(text=" ", callback_data="ph_noop"))
        row.append(InlineKeyboardButton(text="X", callback_data=f"ph_del:{photo_id}"))
        rows.append(row)

    bottom = []
    if len(photos) < max_photos:
        bottom.append(
            InlineKeyboardButton(text="+ Добавить фото", callback_data="ph_add")
        )
    bottom.append(InlineKeyboardButton(text="Готово", callback_data="ph_done"))
    rows.append(bottom)

    return InlineKeyboardMarkup(inline_keyboard=rows)
