from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.profile import Profile, ProfilePhoto


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
