"""
Central event publisher — all services publish events through this module.

Events go to RabbitMQ exchange 'dating_events' via Celery task (fire-and-forget).
This decouples services: they don't call each other, they emit events.

Event types:
  like.created       {from_user_id, to_user_id}
  pass.created       {from_user_id, to_user_id}
  match.created      {match_id, user1_id, user2_id}
  message.created    {match_id, from_user_id, to_user_id, content}
  profile.updated    {user_id}
  profile.deleted    {user_id}
  referral.created   {referrer_id, referred_id}
"""

import logging

logger = logging.getLogger(__name__)


def publish(event_type: str, payload: dict) -> None:
    """Fire-and-forget event publishing via Celery → RabbitMQ."""
    try:
        from src.worker.tasks import publish_event
        publish_event.delay(event_type, payload)
    except Exception:
        logger.warning("Could not publish event %s (broker unavailable?)", event_type)
