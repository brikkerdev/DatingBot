from aiogram.fsm.state import State, StatesGroup


class ChatState(StatesGroup):
    in_chat = State()  # data: match_id, partner_telegram_id, partner_name
