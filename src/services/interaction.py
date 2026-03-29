import logging

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.interaction import Like, Match, Pass
from src.db.models.profile import Profile
from src.db.models.rating import UserRating
from src.metrics import likes_total, matches_total, passes_total
from src.services.events import publish

logger = logging.getLogger(__name__)


async def record_like(
    session: AsyncSession, from_user_id: int, to_user_id: int
) -> Match | None:
    """Record a like. Returns Match if it's mutual, else None."""
    like = Like(from_user_id=from_user_id, to_user_id=to_user_id)
    session.add(like)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return None

    likes_total.inc()
    publish("like.created", {"from_user_id": from_user_id, "to_user_id": to_user_id})

    # Check for mutual like
    mutual = await session.execute(
        select(Like).where(
            Like.from_user_id == to_user_id,
            Like.to_user_id == from_user_id,
        )
    )
    if mutual.scalar_one_or_none() is None:
        await session.commit()
        return None

    # Create match (user1_id < user2_id)
    u1, u2 = sorted([from_user_id, to_user_id])
    match = Match(user1_id=u1, user2_id=u2)
    session.add(match)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return None

    await session.commit()
    await session.refresh(match)

    matches_total.inc()
    publish(
        "match.created",
        {
            "match_id": match.id,
            "user1_id": u1,
            "user2_id": u2,
        },
    )

    return match


async def record_pass(
    session: AsyncSession, from_user_id: int, to_user_id: int
) -> None:
    """Record a pass (skip)."""
    p = Pass(from_user_id=from_user_id, to_user_id=to_user_id)
    session.add(p)
    try:
        await session.commit()
        passes_total.inc()
        publish(
            "pass.created", {"from_user_id": from_user_id, "to_user_id": to_user_id}
        )
    except IntegrityError:
        await session.rollback()


async def get_next_profiles(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[Profile]:
    """Get profiles the user hasn't seen yet, ordered by combined_score desc."""
    seen_subq = (
        select(Like.to_user_id)
        .where(Like.from_user_id == user_id)
        .union_all(select(Pass.to_user_id).where(Pass.from_user_id == user_id))
    ).subquery()

    query = (
        select(Profile)
        .where(
            Profile.user_id != user_id,
            Profile.user_id.notin_(select(seen_subq.c.to_user_id)),
        )
        .outerjoin(UserRating, UserRating.user_id == Profile.user_id)
        .order_by(func.coalesce(UserRating.combined_score, 0).desc(), func.random())
        .limit(limit)
        .options(selectinload(Profile.photos))
    )

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_user_matches(session: AsyncSession, user_id: int) -> list[Match]:
    result = await session.execute(
        select(Match)
        .where(or_(Match.user1_id == user_id, Match.user2_id == user_id))
        .order_by(Match.created_at.desc())
    )
    return list(result.scalars().all())


async def get_match_partner_id(match: Match, user_id: int) -> int:
    return match.user2_id if match.user1_id == user_id else match.user1_id
