"""
Ranking Service — 3-level rating system.

Level 1 (Primary): profile completeness, photos, interests, preferences.
Level 2 (Behavioral): likes received, like/pass ratio, matches, dialog initiation, activity time.
Level 3 (Combined): weighted formula integrating both + referral bonus.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.interaction import Like, Match, Pass
from src.db.models.message import Message
from src.db.models.profile import Profile, ProfilePhoto
from src.db.models.rating import UserRating
from src.db.models.referral import Referral
from src.db.models.user import User


# ---------------------------------------------------------------------------
# Level 1: Primary rating (profile-based, 0..100)
# ---------------------------------------------------------------------------

async def calc_primary_score(session: AsyncSession, user_id: int) -> float:
    profile = (
        await session.execute(
            select(Profile).where(Profile.user_id == user_id)
        )
    ).scalar_one_or_none()

    if not profile:
        return 0.0

    score = 0.0

    # 1) Profile data: age, gender, interests, location
    if profile.name:
        score += 10
    if profile.birth_date:
        score += 5
    if profile.gender:
        score += 5
    if profile.city:
        score += 10

    # 2) Completeness + photos
    if profile.bio:
        score += 15
    interests = profile.interests or []
    score += min(len(interests), 5) * 3

    photo_count = (
        await session.execute(
            select(func.count()).select_from(ProfilePhoto).where(
                ProfilePhoto.profile_id == profile.id
            )
        )
    ).scalar() or 0
    if photo_count >= 1:
        score += 10 + min(photo_count - 1, 5) * 2.5

    # 3) Preferences filled
    if profile.age_min_pref is not None and profile.age_max_pref is not None:
        score += 5
    if profile.preferred_gender:
        score += 5
    if profile.preferred_city:
        score += 5

    return min(score, 100.0)


# ---------------------------------------------------------------------------
# Level 2: Behavioral rating (interaction-based, 0..100)
# ---------------------------------------------------------------------------

async def calc_behavior_score(session: AsyncSession, user_id: int) -> float:
    score = 0.0

    # 1) Likes received: up to 30 pts
    likes_received = (
        await session.execute(
            select(func.count()).select_from(Like).where(Like.to_user_id == user_id)
        )
    ).scalar() or 0
    score += min(likes_received * 2, 30)

    # 2) Like/pass ratio: up to 20 pts
    passes_received = (
        await session.execute(
            select(func.count()).select_from(Pass).where(Pass.to_user_id == user_id)
        )
    ).scalar() or 0
    total = likes_received + passes_received
    if total > 0:
        ratio = likes_received / total
        score += ratio * 20

    # 3) Match frequency: up to 20 pts
    matches_count = (
        await session.execute(
            select(func.count()).select_from(Match).where(
                (Match.user1_id == user_id) | (Match.user2_id == user_id)
            )
        )
    ).scalar() or 0
    score += min(matches_count * 5, 20)

    # 4) Dialog initiation after match: up to 15 pts
    # Count matches where this user sent the FIRST message
    match_ids_subq = (
        select(Match.id).where(
            or_(Match.user1_id == user_id, Match.user2_id == user_id)
        )
    ).subquery()

    # For each match, check if the first message was sent by this user
    first_msg_subq = (
        select(
            Message.match_id,
            func.min(Message.created_at).label("first_at"),
        )
        .where(Message.match_id.in_(select(match_ids_subq.c.id)))
        .group_by(Message.match_id)
    ).subquery()

    dialogs_initiated = (
        await session.execute(
            select(func.count()).select_from(Message).join(
                first_msg_subq,
                and_(
                    Message.match_id == first_msg_subq.c.match_id,
                    Message.created_at == first_msg_subq.c.first_at,
                ),
            ).where(Message.from_user_id == user_id)
        )
    ).scalar() or 0
    score += min(dialogs_initiated * 5, 15)

    # 5) Activity recency: up to 15 pts
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user:
        now = datetime.now(timezone.utc)
        delta = now - user.last_active_at.replace(tzinfo=timezone.utc)
        if delta < timedelta(hours=24):
            score += 15
        elif delta < timedelta(days=7):
            score += 10
        elif delta < timedelta(days=30):
            score += 5

    return min(score, 100.0)


# ---------------------------------------------------------------------------
# Referral bonus (0..100 scale)
# ---------------------------------------------------------------------------

async def calc_referral_bonus(session: AsyncSession, user_id: int) -> float:
    """Each referral gives 20 pts, max 100."""
    count = (
        await session.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == user_id
            )
        )
    ).scalar() or 0
    return min(count * 20, 100.0)


# ---------------------------------------------------------------------------
# Level 3: Combined rating (weighted formula)
# ---------------------------------------------------------------------------

def calc_combined_score(primary: float, behavioral: float, referral_bonus: float = 0) -> float:
    """
    Combined = 0.4 * primary + 0.5 * behavioral + 0.1 * referral_bonus
    All inputs on 0..100 scale.
    """
    return 0.4 * primary + 0.5 * behavioral + 0.1 * referral_bonus


# ---------------------------------------------------------------------------
# Full recalculation for one user
# ---------------------------------------------------------------------------

async def recalculate_user_rating(session: AsyncSession, user_id: int) -> UserRating:
    primary = await calc_primary_score(session, user_id)
    behavioral = await calc_behavior_score(session, user_id)
    referral = await calc_referral_bonus(session, user_id)
    combined = calc_combined_score(primary, behavioral, referral)

    rating = (
        await session.execute(
            select(UserRating).where(UserRating.user_id == user_id)
        )
    ).scalar_one_or_none()

    if rating:
        rating.primary_score = primary
        rating.behavior_score = behavioral
        rating.combined_score = combined
        rating.updated_at = func.now()
    else:
        rating = UserRating(
            user_id=user_id,
            primary_score=primary,
            behavior_score=behavioral,
            combined_score=combined,
        )
        session.add(rating)

    await session.commit()
    await session.refresh(rating)
    return rating


# ---------------------------------------------------------------------------
# Batch recalculation (for Celery periodic task)
# ---------------------------------------------------------------------------

async def recalculate_all_ratings(session: AsyncSession) -> int:
    """Recalculate ratings for all active users. Returns count."""
    result = await session.execute(
        select(User.id).where(User.is_active.is_(True))
    )
    user_ids = list(result.scalars().all())

    for uid in user_ids:
        await recalculate_user_rating(session, uid)

    return len(user_ids)
