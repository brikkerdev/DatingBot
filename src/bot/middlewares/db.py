from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models.user import User


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker) -> None:
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_pool() as session:
            data["session"] = session
            result = await handler(event, data)

            # Update last_active_at for the user
            tg_user = data.get("event_from_user")
            if tg_user:
                from sqlalchemy import func

                await session.execute(
                    update(User)
                    .where(User.telegram_id == tg_user.id)
                    .values(last_active_at=func.now())
                )
                await session.commit()

            return result
