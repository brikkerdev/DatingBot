import logging
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.interaction import Like, Match, Pass
from src.db.models.profile import Profile, ProfilePhoto
from src.services.events import publish

logger = logging.getLogger(__name__)


async def _invalidate_cache() -> None:
    """Invalidate Redis profile queues directly — no MQ needed for local cache ops."""
    try:
        from redis.asyncio import Redis
        from src.config import settings

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        keys = await redis.keys("profile_queue:*")
        if keys:
            await redis.delete(*keys)
            logger.info("Invalidated %d profile queues", len(keys))
        await redis.aclose()
    except Exception:
        logger.warning("Cache invalidation failed (Redis unavailable?)")


async def get_profile_by_user_id(session: AsyncSession, user_id: int) -> Profile | None:
    result = await session.execute(
        select(Profile)
        .where(Profile.user_id == user_id)
        .options(selectinload(Profile.photos))
    )
    return result.scalar_one_or_none()


async def create_profile(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    birth_date: date,
    gender: str,
    city: str,
    bio: str | None = None,
) -> Profile:
    profile = Profile(
        user_id=user_id,
        name=name,
        birth_date=birth_date,
        gender=gender,
        city=city,
        bio=bio,
    )
    session.add(profile)
    await session.flush()
    return profile


async def add_photo(
    session: AsyncSession,
    profile_id: int,
    storage_path: str,
    sort_order: int = 0,
) -> ProfilePhoto:
    photo = ProfilePhoto(
        profile_id=profile_id,
        storage_path=storage_path,
        sort_order=sort_order,
    )
    session.add(photo)
    await session.flush()
    return photo


async def update_profile(
    session: AsyncSession,
    profile: Profile,
    **fields: Any,
) -> Profile:
    for key, value in fields.items():
        if hasattr(profile, key):
            setattr(profile, key, value)
    await session.commit()
    await session.refresh(profile)
    # Ranking recalc via MQ (heavy operation, async is better)
    publish("profile.updated", {"user_id": profile.user_id})
    # Cache invalidation directly (cheap operation, no need for MQ)
    await _invalidate_cache()
    return profile


async def replace_photos(
    session: AsyncSession,
    profile_id: int,
    storage_paths: list[str],
) -> None:
    await session.execute(
        delete(ProfilePhoto).where(ProfilePhoto.profile_id == profile_id)
    )
    for i, path in enumerate(storage_paths):
        session.add(
            ProfilePhoto(profile_id=profile_id, storage_path=path, sort_order=i)
        )
    await session.commit()


async def delete_photo(session: AsyncSession, photo_id: int) -> None:
    await session.execute(delete(ProfilePhoto).where(ProfilePhoto.id == photo_id))
    await session.commit()


async def swap_photo_order(
    session: AsyncSession,
    photo_id_a: int,
    photo_id_b: int,
) -> None:
    a = (
        await session.execute(select(ProfilePhoto).where(ProfilePhoto.id == photo_id_a))
    ).scalar_one_or_none()
    b = (
        await session.execute(select(ProfilePhoto).where(ProfilePhoto.id == photo_id_b))
    ).scalar_one_or_none()
    if a and b:
        a.sort_order, b.sort_order = b.sort_order, a.sort_order
        await session.commit()


async def get_photo_by_id(session: AsyncSession, photo_id: int) -> ProfilePhoto | None:
    result = await session.execute(
        select(ProfilePhoto).where(ProfilePhoto.id == photo_id)
    )
    return result.scalar_one_or_none()


async def delete_profile(
    session: AsyncSession, profile_id: int, user_id: int = 0
) -> None:
    await session.execute(delete(Profile).where(Profile.id == profile_id))
    if user_id:
        await session.execute(
            delete(Like).where(
                (Like.from_user_id == user_id) | (Like.to_user_id == user_id)
            )
        )
        await session.execute(
            delete(Pass).where(
                (Pass.from_user_id == user_id) | (Pass.to_user_id == user_id)
            )
        )
        await session.execute(
            delete(Match).where(
                (Match.user1_id == user_id) | (Match.user2_id == user_id)
            )
        )
    await session.commit()
    if user_id:
        publish("profile.deleted", {"user_id": user_id})
    await _invalidate_cache()
