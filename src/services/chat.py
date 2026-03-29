import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.interaction import Match
from src.db.models.message import Message
from src.metrics import messages_total
from src.services.events import publish

logger = logging.getLogger(__name__)


async def get_match_by_id(session: AsyncSession, match_id: int) -> Match | None:
    result = await session.execute(select(Match).where(Match.id == match_id))
    return result.scalar_one_or_none()


async def is_user_in_match(match: Match, user_id: int) -> bool:
    return user_id in (match.user1_id, match.user2_id)


async def send_message(
    session: AsyncSession,
    match_id: int,
    from_user_id: int,
    content: str,
) -> Message:
    msg = Message(match_id=match_id, from_user_id=from_user_id, content=content)
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    messages_total.inc()

    # MQ event only for ranking recalculation (dialog initiation score).
    # Message forwarding is done directly by the bot handler — chat must be instant.
    publish("message.created", {
        "match_id": match_id,
        "from_user_id": from_user_id,
    })

    return msg


async def get_messages(
    session: AsyncSession,
    match_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.match_id == match_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(reversed(result.scalars().all()))
