"""
Celery tasks for the dating bot.

- recalculate_ratings: periodic recalculation of all user ratings
- publish_event: send interaction events to RabbitMQ for service communication
"""

import json
import logging
import time

from sqlalchemy import and_, create_engine, func as sa_func, or_, select
from sqlalchemy.orm import Session

from src.config import settings
from src.worker.celery_app import app

logger = logging.getLogger(__name__)

_sync_engine = None


def get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync, echo=False)
    return _sync_engine


def _recalc_one(session: Session, uid: int) -> None:
    """Recalculate rating for a single user (sync)."""
    from src.db.models.user import User
    from src.db.models.profile import Profile, ProfilePhoto
    from src.db.models.interaction import Like, Pass, Match
    from src.db.models.message import Message
    from src.db.models.rating import UserRating
    from src.db.models.referral import Referral

    profile = session.execute(
        select(Profile).where(Profile.user_id == uid)
    ).scalar_one_or_none()

    # Primary
    primary = 0.0
    if profile:
        if profile.name: primary += 10
        if profile.birth_date: primary += 5
        if profile.gender: primary += 5
        if profile.city: primary += 10
        if profile.bio: primary += 15
        interests = profile.interests or []
        primary += min(len(interests), 5) * 3
        photo_count = session.execute(
            select(sa_func.count()).select_from(ProfilePhoto).where(
                ProfilePhoto.profile_id == profile.id
            )
        ).scalar() or 0
        if photo_count >= 1:
            primary += 10 + min(photo_count - 1, 5) * 2.5
        if profile.age_min_pref is not None and profile.age_max_pref is not None:
            primary += 5
        if profile.preferred_gender: primary += 5
        if profile.preferred_city: primary += 5
    primary = min(primary, 100.0)

    # Behavioral
    likes = session.execute(
        select(sa_func.count()).select_from(Like).where(Like.to_user_id == uid)
    ).scalar() or 0
    passes = session.execute(
        select(sa_func.count()).select_from(Pass).where(Pass.to_user_id == uid)
    ).scalar() or 0
    matches = session.execute(
        select(sa_func.count()).select_from(Match).where(
            (Match.user1_id == uid) | (Match.user2_id == uid)
        )
    ).scalar() or 0

    behavioral = min(likes * 2, 30)
    total = likes + passes
    if total > 0:
        behavioral += (likes / total) * 20
    behavioral += min(matches * 5, 20)

    # Dialog initiation
    match_ids = [r[0] for r in session.execute(
        select(Match.id).where((Match.user1_id == uid) | (Match.user2_id == uid))
    ).all()]
    if match_ids:
        first_msgs = session.execute(
            select(Message.match_id, sa_func.min(Message.created_at).label("first_at"))
            .where(Message.match_id.in_(match_ids))
            .group_by(Message.match_id)
        ).all()
        initiated = 0
        for mid, first_at in first_msgs:
            fm = session.execute(
                select(Message).where(Message.match_id == mid, Message.created_at == first_at)
            ).scalar_one_or_none()
            if fm and fm.from_user_id == uid:
                initiated += 1
        behavioral += min(initiated * 5, 15)

    # Activity recency
    from datetime import datetime, timedelta, timezone
    user = session.execute(select(User).where(User.id == uid)).scalar_one_or_none()
    if user:
        now = datetime.now(timezone.utc)
        delta = now - user.last_active_at.replace(tzinfo=timezone.utc)
        if delta < timedelta(hours=24): behavioral += 15
        elif delta < timedelta(days=7): behavioral += 10
        elif delta < timedelta(days=30): behavioral += 5
    behavioral = min(behavioral, 100.0)

    # Referral bonus
    ref_count = session.execute(
        select(sa_func.count()).select_from(Referral).where(Referral.referrer_id == uid)
    ).scalar() or 0
    referral = min(ref_count * 20, 100.0)

    combined = 0.4 * primary + 0.5 * behavioral + 0.1 * referral

    rating = session.execute(
        select(UserRating).where(UserRating.user_id == uid)
    ).scalar_one_or_none()
    if rating:
        rating.primary_score = primary
        rating.behavior_score = behavioral
        rating.combined_score = combined
    else:
        session.add(UserRating(
            user_id=uid, primary_score=primary,
            behavior_score=behavioral, combined_score=combined,
        ))


@app.task(name="src.worker.tasks.recalculate_ratings")
def recalculate_ratings() -> dict:
    """Periodic task: recalculate all user ratings."""
    from src.db.models.user import User

    start = time.time()
    engine = get_sync_engine()
    count = 0

    with Session(engine) as session:
        user_ids = session.execute(
            select(User.id).where(User.is_active.is_(True))
        ).scalars().all()

        for uid in user_ids:
            _recalc_one(session, uid)
            count += 1

        session.commit()

    elapsed = time.time() - start
    logger.info("Recalculated ratings for %d users in %.2fs", count, elapsed)
    return {"recalculated": count, "elapsed_seconds": round(elapsed, 2)}


@app.task(name="src.worker.tasks.publish_event")
def publish_event(event_type: str, payload: dict) -> None:
    """Publish an event to RabbitMQ exchange for inter-service communication."""
    import pika

    try:
        connection = pika.BlockingConnection(
            pika.URLParameters(settings.rabbitmq_url)
        )
        channel = connection.channel()
        channel.exchange_declare(exchange="dating_events", exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange="dating_events",
            routing_key=event_type,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
        logger.info("Published event %s: %s", event_type, payload)
    except Exception:
        logger.exception("Failed to publish event %s", event_type)
