"""
Seed test profiles to demonstrate matching and 3-level ranking.

Usage:
    python -m scripts.seed_test_profiles

Creates 12 users in the telegram_id range 900_000_001..900_000_012,
with varied profile completeness and interaction history so the
primary/behavior/combined scores span the full 0..100 range.

Idempotent: existing users in this range are deleted and re-created.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import delete, select

from src.config import settings
from src.db.engine import session_factory
from src.db.models.interaction import Match
from src.db.models.message import Message
from src.db.models.profile import Profile, ProfilePhoto
from src.db.models.rating import UserRating
from src.db.models.referral import Referral
from src.db.models.user import User
from src.services.interaction import record_like, record_pass
from src.services.ranking import recalculate_user_rating
from src.services.storage import ensure_bucket, get_s3_client

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed")

TEST_TG_RANGE_START = 900_000_001
TEST_TG_RANGE_END = 900_000_099

# Minimal valid 1x1 JPEG — embedded so the seed is offline-safe.
# resolve_photo downloads this from Minio on each browse.
_PLACEHOLDER_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
    "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR"
    "CAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA"
    "AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
    "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG"
    "h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl"
    "5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk"
    "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOE"
    "hYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=="
)
PLACEHOLDER_JPEG = base64.b64decode(_PLACEHOLDER_JPEG_B64)


def _photo_key(seed_key: str, idx: int) -> str:
    return f"photos/seed_{seed_key}_{idx}.jpg"


@dataclass
class Seed:
    key: str
    telegram_id: int
    name: str
    birth_year: int
    gender: str
    city: str | None
    bio: str | None
    interests: list[str]
    photos: int
    age_pref: tuple[int, int] | None
    preferred_gender: str | None
    preferred_city: str | None
    active_ago: timedelta = timedelta(minutes=5)
    # filled later with the DB id
    user_id: int = 0
    profile_id: int = 0
    likes_given: list[str] = field(default_factory=list)
    passes_given: list[str] = field(default_factory=list)
    referred_by: str | None = None
    initiates_chat_with: list[str] = field(default_factory=list)


SEEDS: list[Seed] = [
    Seed(
        key="alice",
        telegram_id=900_000_001,
        name="Алиса",
        birth_year=2002,
        gender="female",
        city="Москва",
        bio="Люблю путешествовать, читать и ходить на выставки.",
        interests=["travel", "books", "art", "yoga", "coffee"],
        photos=5,
        age_pref=(24, 32),
        preferred_gender="male",
        preferred_city="Москва",
        active_ago=timedelta(minutes=5),
        likes_given=["boris", "ivan", "leonid", "denis", "maria"],
        passes_given=["fyodor"],
        initiates_chat_with=["boris", "ivan", "leonid"],
    ),
    Seed(
        key="boris",
        telegram_id=900_000_002,
        name="Борис",
        birth_year=1997,
        gender="male",
        city="Москва",
        bio="Разработчик, бегаю по утрам, варю фильтр-кофе.",
        interests=["coding", "running", "coffee", "music"],
        photos=3,
        age_pref=(22, 28),
        preferred_gender="female",
        preferred_city="Москва",
        active_ago=timedelta(hours=2),
        likes_given=["alice", "clara", "maria"],
        passes_given=["galina"],
        initiates_chat_with=["maria"],
        referred_by="alice",
    ),
    Seed(
        key="clara",
        telegram_id=900_000_003,
        name="Клара",
        birth_year=2000,
        gender="female",
        city="Москва",
        bio="Архитектор, обожаю город и хороший свет.",
        interests=["architecture", "photo", "travel"],
        photos=3,
        age_pref=(25, 33),
        preferred_gender="male",
        preferred_city="Москва",
        active_ago=timedelta(hours=4),
        likes_given=["boris", "ivan", "alice"],
        passes_given=["fyodor"],
        initiates_chat_with=["boris"],
        referred_by="alice",
    ),
    Seed(
        key="denis",
        telegram_id=900_000_004,
        name="Денис",
        birth_year=1995,
        gender="male",
        city="Санкт-Петербург",
        bio="Инженер, велосипед, настолки.",
        interests=["engineering", "cycling", "boardgames"],
        photos=2,
        age_pref=(22, 30),
        preferred_gender="female",
        preferred_city=None,
        active_ago=timedelta(days=3),
        likes_given=["alice", "katya"],
        passes_given=["galina"],
    ),
    Seed(
        key="elena",
        telegram_id=900_000_005,
        name="Елена",
        birth_year=2003,
        gender="female",
        city="Москва",
        bio="Студентка, танцы, языки.",
        interests=["dancing", "languages", "cinema", "music"],
        photos=3,
        age_pref=(21, 27),
        preferred_gender="male",
        preferred_city="Москва",
        active_ago=timedelta(minutes=30),
        likes_given=["alice"],
        referred_by="alice",
    ),
    Seed(
        key="fyodor",
        telegram_id=900_000_006,
        name="Фёдор",
        birth_year=1990,
        gender="male",
        city="Санкт-Петербург",
        bio=None,
        interests=[],
        photos=1,
        age_pref=None,
        preferred_gender=None,
        preferred_city=None,
        active_ago=timedelta(days=10),
        likes_given=["alice", "clara"],
    ),
    Seed(
        key="galina",
        telegram_id=900_000_007,
        name="Галина",
        birth_year=1998,
        gender="female",
        city=None,
        bio=None,
        interests=[],
        photos=0,
        age_pref=None,
        preferred_gender=None,
        preferred_city=None,
        active_ago=timedelta(days=40),
        likes_given=[],
        passes_given=["alice"],
    ),
    Seed(
        key="ivan",
        telegram_id=900_000_008,
        name="Иван",
        birth_year=1996,
        gender="male",
        city="Москва",
        bio="Музыкант, кофе и книги.",
        interests=["music", "books", "coffee"],
        photos=2,
        age_pref=(22, 30),
        preferred_gender="female",
        preferred_city="Москва",
        active_ago=timedelta(hours=6),
        likes_given=["alice", "clara", "katya"],
        passes_given=["galina"],
        initiates_chat_with=["clara"],
    ),
    Seed(
        key="katya",
        telegram_id=900_000_009,
        name="Катя",
        birth_year=2001,
        gender="female",
        city="Москва",
        bio="Дизайнер, бег и кино. Иногда рисую.",
        interests=["design", "running", "cinema", "art"],
        photos=4,
        age_pref=(24, 32),
        preferred_gender="male",
        preferred_city="Москва",
        active_ago=timedelta(hours=1),
        likes_given=["denis", "nikolay", "boris"],
        passes_given=["fyodor"],
        initiates_chat_with=["denis", "nikolay"],
    ),
    Seed(
        key="leonid",
        telegram_id=900_000_010,
        name="Леонид",
        birth_year=1993,
        gender="male",
        city="Санкт-Петербург",
        bio="Финансы, кино, сноуборд.",
        interests=["finance", "cinema", "snowboard"],
        photos=2,
        age_pref=(22, 30),
        preferred_gender="female",
        preferred_city=None,
        active_ago=timedelta(days=2),
        likes_given=["alice"],
        passes_given=["galina"],
    ),
    Seed(
        key="maria",
        telegram_id=900_000_011,
        name="Мария",
        birth_year=1999,
        gender="female",
        city="Москва",
        bio="Журналист, йога, кофе.",
        interests=["writing", "yoga", "coffee"],
        photos=3,
        age_pref=(25, 33),
        preferred_gender="male",
        preferred_city="Москва",
        active_ago=timedelta(minutes=45),
        likes_given=["boris", "alice"],
        passes_given=["fyodor"],
    ),
    Seed(
        key="nikolay",
        telegram_id=900_000_012,
        name="Николай",
        birth_year=1992,
        gender="male",
        city="Москва",
        bio="Менеджер, горы и шахматы.",
        interests=["mountains", "chess"],
        photos=1,
        age_pref=(22, 30),
        preferred_gender="female",
        preferred_city=None,
        active_ago=timedelta(days=5),
        likes_given=["alice", "katya"],
    ),
]


async def wipe_test_users() -> None:
    async with session_factory() as session:
        rows = await session.execute(
            select(User.id).where(
                User.telegram_id.between(TEST_TG_RANGE_START, TEST_TG_RANGE_END)
            )
        )
        ids = list(rows.scalars().all())
        if not ids:
            return
        await session.execute(delete(User).where(User.id.in_(ids)))
        await session.commit()
        log.info("Removed %d previous test users.", len(ids))


async def create_users_and_profiles() -> None:
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        for s in SEEDS:
            user = User(
                telegram_id=s.telegram_id,
                last_active_at=now - s.active_ago,
            )
            session.add(user)
            await session.flush()
            s.user_id = user.id

            profile = Profile(
                user_id=user.id,
                name=s.name,
                birth_date=date(s.birth_year, 6, 15),
                gender=s.gender,
                city=s.city,
                bio=s.bio,
                interests=s.interests,
                age_min_pref=s.age_pref[0] if s.age_pref else None,
                age_max_pref=s.age_pref[1] if s.age_pref else None,
                preferred_gender=s.preferred_gender,
                preferred_city=s.preferred_city,
            )
            session.add(profile)
            await session.flush()
            s.profile_id = profile.id

            for i in range(s.photos):
                session.add(
                    ProfilePhoto(
                        profile_id=profile.id,
                        storage_path=_photo_key(s.key, i),
                        sort_order=i,
                    )
                )
        await session.commit()
    log.info("Created %d users with profiles.", len(SEEDS))


def _by_key() -> dict[str, Seed]:
    return {s.key: s for s in SEEDS}


async def clear_browse_queues() -> int:
    redis = Redis.from_url(settings.redis_url)
    try:
        keys = await redis.keys("profile_queue:*")
        if keys:
            await redis.delete(*keys)
        return len(keys)
    finally:
        await redis.aclose()


async def upload_placeholder_photos() -> int:
    """Put a tiny JPEG at each seed_<key>_<i>.jpg key so resolve_photo works."""
    await ensure_bucket()
    client = get_s3_client()
    count = 0
    for s in SEEDS:
        for i in range(s.photos):
            await client.put_object(
                settings.minio_bucket,
                _photo_key(s.key, i),
                io.BytesIO(PLACEHOLDER_JPEG),
                length=len(PLACEHOLDER_JPEG),
                content_type="image/jpeg",
            )
            count += 1
    return count


async def create_referrals() -> None:
    by = _by_key()
    async with session_factory() as session:
        for s in SEEDS:
            if not s.referred_by:
                continue
            session.add(
                Referral(
                    referrer_id=by[s.referred_by].user_id,
                    referred_id=s.user_id,
                )
            )
        await session.commit()


async def create_interactions() -> tuple[int, int, int]:
    """Replay likes/passes through the real service so matches emerge naturally."""
    by = _by_key()
    likes = passes = matches = 0

    async with session_factory() as session:
        for s in SEEDS:
            for target in s.passes_given:
                await record_pass(session, s.user_id, by[target].user_id)
                passes += 1
            for target in s.likes_given:
                m = await record_like(session, s.user_id, by[target].user_id)
                likes += 1
                if m is not None:
                    matches += 1
    return likes, passes, matches


async def create_messages() -> int:
    """Insert messages so the 'dialog initiation' bonus kicks in."""
    by = _by_key()
    count = 0
    async with session_factory() as session:
        for s in SEEDS:
            for target in s.initiates_chat_with:
                u1, u2 = sorted([s.user_id, by[target].user_id])
                match = (
                    await session.execute(
                        select(Match).where(
                            Match.user1_id == u1, Match.user2_id == u2
                        )
                    )
                ).scalar_one_or_none()
                if match is None:
                    # No mutual like — can't have a chat.
                    continue
                base = datetime.now(timezone.utc) - timedelta(days=1)
                session.add(
                    Message(
                        match_id=match.id,
                        from_user_id=s.user_id,
                        content=f"Привет, {by[target].name}!",
                        created_at=base,
                    )
                )
                session.add(
                    Message(
                        match_id=match.id,
                        from_user_id=by[target].user_id,
                        content="Привет!",
                        created_at=base + timedelta(minutes=3),
                    )
                )
                count += 2
        await session.commit()
    return count


async def recalc_all() -> list[tuple[Seed, UserRating]]:
    results: list[tuple[Seed, UserRating]] = []
    async with session_factory() as session:
        for s in SEEDS:
            rating = await recalculate_user_rating(session, s.user_id)
            results.append((s, rating))
    return results


def print_leaderboard(results: list[tuple[Seed, UserRating]]) -> None:
    results.sort(key=lambda r: float(r[1].combined_score), reverse=True)
    log.info("")
    log.info("=" * 74)
    log.info(
        f"{'#':>2}  {'name':<12}{'tg_id':>12}  {'primary':>8}  "
        f"{'behav':>8}  {'combined':>10}"
    )
    log.info("-" * 74)
    for i, (s, r) in enumerate(results, 1):
        log.info(
            f"{i:>2}  {s.name:<12}{s.telegram_id:>12}  "
            f"{float(r.primary_score):>8.2f}  {float(r.behavior_score):>8.2f}  "
            f"{float(r.combined_score):>10.2f}"
        )
    log.info("=" * 74)


async def count_matches() -> int:
    async with session_factory() as session:
        rows = await session.execute(select(Match.id))
        return len(list(rows.scalars().all()))


async def main() -> None:
    log.info("Seeding test profiles...")
    await wipe_test_users()
    await create_users_and_profiles()
    photos = await upload_placeholder_photos()
    log.info("Uploaded %d placeholder photos to Minio.", photos)
    cleared = await clear_browse_queues()
    if cleared:
        log.info("Cleared %d stale Redis browse queues.", cleared)
    await create_referrals()
    likes, passes, matches = await create_interactions()
    msgs = await create_messages()
    total_matches = await count_matches()
    log.info(
        "Likes=%d  Passes=%d  Matches(new)=%d  MatchesTotal=%d  Messages=%d",
        likes,
        passes,
        matches,
        total_matches,
        msgs,
    )
    results = await recalc_all()
    print_leaderboard(results)
    log.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
