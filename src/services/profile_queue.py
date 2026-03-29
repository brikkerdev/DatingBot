"""
Redis-backed profile queue.

When user starts browsing:
  1. First profile goes through the full service path (DB → ranking → response).
  2. Simultaneously, 10 next profiles are pre-loaded into a Redis list.
  3. Subsequent requests pop from Redis (fast).
  4. When the Redis queue is empty, the cycle repeats.
"""

import json
import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.metrics import queue_fills, queue_hits, queue_misses
from src.services.interaction import get_next_profiles

logger = logging.getLogger(__name__)

QUEUE_KEY_PREFIX = "profile_queue:"
QUEUE_SIZE = 10
QUEUE_TTL = 600  # 10 minutes


def _key(user_id: int) -> str:
    return f"{QUEUE_KEY_PREFIX}{user_id}"


async def fill_queue(
    redis: Redis,
    session: AsyncSession,
    user_id: int,
) -> int:
    """Load next profiles into Redis list. Returns count loaded."""
    profiles = await get_next_profiles(session, user_id, limit=QUEUE_SIZE)

    if not profiles:
        return 0

    key = _key(user_id)
    pipe = redis.pipeline()
    await pipe.delete(key)

    for p in profiles:
        data = json.dumps({
            "user_id": p.user_id,
            "name": p.name,
            "birth_date": p.birth_date.isoformat(),
            "gender": p.gender,
            "city": p.city or "",
            "bio": p.bio or "",
            "photo": p.photos[0].storage_path if p.photos else "",
        })
        await pipe.rpush(key, data)

    await pipe.expire(key, QUEUE_TTL)
    await pipe.execute()

    queue_fills.inc()
    logger.info("Filled profile queue for user %s: %d profiles", user_id, len(profiles))
    return len(profiles)


async def pop_profile(redis: Redis, user_id: int) -> dict | None:
    """Pop next profile from the Redis queue. Returns dict or None if empty."""
    key = _key(user_id)
    data = await redis.lpop(key)
    if data is None:
        queue_misses.inc()
        return None
    queue_hits.inc()
    return json.loads(data)


async def queue_length(redis: Redis, user_id: int) -> int:
    """How many profiles remain in the queue."""
    return await redis.llen(_key(user_id))
