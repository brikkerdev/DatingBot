from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.referral import Referral
from src.services.events import publish


async def create_referral(
    session: AsyncSession, referrer_id: int, referred_id: int
) -> bool:
    """Record a referral. Returns True if new, False if already exists."""
    ref = Referral(referrer_id=referrer_id, referred_id=referred_id)
    session.add(ref)
    try:
        await session.commit()
        publish(
            "referral.created", {"referrer_id": referrer_id, "referred_id": referred_id}
        )
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def get_referral_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Referral)
        .where(Referral.referrer_id == user_id)
    )
    return result.scalar() or 0
