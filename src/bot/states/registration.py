from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_city = State()
    waiting_for_bio = State()
    waiting_for_photo = State()
    confirm = State()


class EditProfileState(StatesGroup):
    choosing_field = State()
    editing_name = State()
    editing_age = State()
    editing_gender = State()
    editing_city = State()
    editing_bio = State()
    editing_photo = State()
