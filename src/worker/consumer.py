"""
RabbitMQ event consumer — inter-service communication.

WHY MQ and not direct calls:
  Rating recalculation is a heavy operation (8+ SQL queries per user).
  If done synchronously inside the like/pass handler, every swipe takes
  200-500ms extra. Through MQ the user gets instant feedback, and the
  ranking service recalculates in the background.

  Match notifications go through MQ because the partner is not in the
  current request context — the notification is fire-and-forget and
  doesn't need to block the user who swiped.

  Chat message forwarding is NOT done through MQ — it's done directly
  by the bot handler because chat must be instant.

  Cache invalidation is NOT done through MQ — it's a single Redis call,
  MQ overhead would be more expensive than the operation itself.

Services:

1. Ranking Service (queue: ranking_service)
   Listens: like.created, pass.created, match.created, message.created,
            referral.created, profile.updated, profile.deleted
   Action:  Recalculates user rating in the background

2. Notification Service (queue: notification_service)
   Listens: match.created
   Action:  Sends "You have a match!" notification to both users via Telegram

Run: python -m src.worker.consumer
"""

import json
import logging

import pika
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import create_engine, select, func as sa_func
from sqlalchemy.orm import Session

from src.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url_sync, echo=False)
    return _engine


# ──────────────────────────────────────────────────────
# Ranking Service
# ──────────────────────────────────────────────────────

def _recalc_rating(session: Session, user_id: int) -> None:
    """Full rating recalculation — expensive (8+ queries), that's why it's async via MQ."""
    from src.db.models.user import User
    from src.db.models.profile import Profile, ProfilePhoto
    from src.db.models.interaction import Like, Pass, Match
    from src.db.models.message import Message
    from src.db.models.rating import UserRating
    from src.db.models.referral import Referral
    from datetime import datetime, timedelta, timezone

    profile = session.execute(
        select(Profile).where(Profile.user_id == user_id)
    ).scalar_one_or_none()

    primary = 0.0
    if profile:
        if profile.name:
            primary += 10
        if profile.birth_date:
            primary += 5
        if profile.gender:
            primary += 5
        if profile.city:
            primary += 10
        if profile.bio:
            primary += 15
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
        if profile.preferred_gender:
            primary += 5
        if profile.preferred_city:
            primary += 5
    primary = min(primary, 100.0)

    likes = session.execute(
        select(sa_func.count()).select_from(Like).where(Like.to_user_id == user_id)
    ).scalar() or 0
    passes = session.execute(
        select(sa_func.count()).select_from(Pass).where(Pass.to_user_id == user_id)
    ).scalar() or 0
    matches = session.execute(
        select(sa_func.count()).select_from(Match).where(
            (Match.user1_id == user_id) | (Match.user2_id == user_id)
        )
    ).scalar() or 0

    behavioral = min(likes * 2, 30)
    total = likes + passes
    if total > 0:
        behavioral += (likes / total) * 20
    behavioral += min(matches * 5, 20)

    # Dialog initiation — count matches where this user sent the first message
    match_ids = [r[0] for r in session.execute(
        select(Match.id).where((Match.user1_id == user_id) | (Match.user2_id == user_id))
    ).all()]
    if match_ids:
        first_msgs = session.execute(
            select(Message.match_id, sa_func.min(Message.created_at).label("t"))
            .where(Message.match_id.in_(match_ids)).group_by(Message.match_id)
        ).all()
        initiated = 0
        for mid, t in first_msgs:
            fm = session.execute(
                select(Message).where(Message.match_id == mid, Message.created_at == t)
            ).scalar_one_or_none()
            if fm and fm.from_user_id == user_id:
                initiated += 1
        behavioral += min(initiated * 5, 15)

    user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user:
        now = datetime.now(timezone.utc)
        delta = now - user.last_active_at.replace(tzinfo=timezone.utc)
        if delta < timedelta(hours=24):
            behavioral += 15
        elif delta < timedelta(days=7):
            behavioral += 10
        elif delta < timedelta(days=30):
            behavioral += 5
    behavioral = min(behavioral, 100.0)

    ref_count = session.execute(
        select(sa_func.count()).select_from(Referral).where(Referral.referrer_id == user_id)
    ).scalar() or 0
    referral = min(ref_count * 20, 100.0)

    combined = 0.4 * primary + 0.5 * behavioral + 0.1 * referral

    rating = session.execute(select(UserRating).where(UserRating.user_id == user_id)).scalar_one_or_none()
    if rating:
        rating.primary_score = primary
        rating.behavior_score = behavioral
        rating.combined_score = combined
    else:
        session.add(UserRating(user_id=user_id, primary_score=primary,
                               behavior_score=behavioral, combined_score=combined))
    session.commit()


def handle_ranking(event_type: str, payload: dict) -> None:
    engine = get_engine()
    with Session(engine) as session:
        if event_type in ("like.created", "pass.created"):
            _recalc_rating(session, payload["to_user_id"])
        elif event_type == "match.created":
            _recalc_rating(session, payload["user1_id"])
            _recalc_rating(session, payload["user2_id"])
        elif event_type == "message.created":
            _recalc_rating(session, payload["from_user_id"])
        elif event_type == "referral.created":
            _recalc_rating(session, payload["referrer_id"])
        elif event_type == "profile.updated":
            _recalc_rating(session, payload["user_id"])
        elif event_type == "profile.deleted":
            from src.db.models.rating import UserRating
            session.execute(
                UserRating.__table__.delete().where(UserRating.user_id == payload["user_id"])
            )
            session.commit()
    logger.info("[ranking] %s → recalculated", event_type)


# ──────────────────────────────────────────────────────
# Notification Service
# ──────────────────────────────────────────────────────

def handle_notification(event_type: str, payload: dict) -> None:
    """Send match notifications via Telegram.

    Only match.created goes through MQ because the partner user is not
    in the current request context. The user who swiped gets notified
    directly in the handler (instant feedback).
    """
    import asyncio

    if event_type != "match.created":
        return

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    async def _notify():
        try:
            engine = get_engine()
            with Session(engine) as session:
                from src.db.models.user import User
                from src.db.models.profile import Profile

                for uid_key, partner_key in [("user1_id", "user2_id"), ("user2_id", "user1_id")]:
                    user = session.execute(
                        select(User).where(User.id == payload[uid_key])
                    ).scalar_one_or_none()
                    partner_profile = session.execute(
                        select(Profile).where(Profile.user_id == payload[partner_key])
                    ).scalar_one_or_none()
                    name = partner_profile.name if partner_profile else "Кто-то"
                    if user:
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                f"<b>Мэтч!</b> Вы понравились <b>{name}</b>!\n"
                                f"Загляните в «Мэтчи», чтобы начать общение.",
                            )
                        except Exception:
                            logger.warning("Failed to notify user %s", user.telegram_id)
        finally:
            await bot.session.close()

    asyncio.run(_notify())
    logger.info("[notification] match.created → notified both users")


# ──────────────────────────────────────────────────────
# Main — start consumer with both queues
# ──────────────────────────────────────────────────────

ROUTING = {
    "ranking_service": {
        "events": [
            "like.created", "pass.created", "match.created",
            "message.created", "referral.created",
            "profile.updated", "profile.deleted",
        ],
        "handler": handle_ranking,
    },
    "notification_service": {
        "events": ["match.created"],
        "handler": handle_notification,
    },
}


def make_callback(handler):
    def on_message(ch, method, properties, body):
        event_type = method.routing_key
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON: %s", body)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        try:
            handler(event_type, payload)
        except Exception:
            logger.exception("Error processing %s", event_type)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    return on_message


def main():
    logger.info("Starting event consumer...")
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.exchange_declare(exchange="dating_events", exchange_type="topic", durable=True)

    for queue_name, cfg in ROUTING.items():
        channel.queue_declare(queue=queue_name, durable=True)
        for event in cfg["events"]:
            channel.queue_bind(exchange="dating_events", queue=queue_name, routing_key=event)
        channel.basic_consume(queue=queue_name, on_message_callback=make_callback(cfg["handler"]))
        logger.info("  %s → %s", queue_name, cfg["events"])

    channel.basic_qos(prefetch_count=1)
    logger.info("Consumer ready (ranking + notification)")

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    connection.close()


if __name__ == "__main__":
    main()
