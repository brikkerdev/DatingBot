from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.user import User


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> tuple[User, bool]:
    """Get existing user or create a new one. Returns (user, is_new)."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        return user, False

    user = User(telegram_id=telegram_id)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one()
        return user, False

    await session.refresh(user)
    return user, True


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()
