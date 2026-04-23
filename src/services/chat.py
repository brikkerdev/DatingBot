import logging

from sqlalchemy import func, select, update
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
    *,
    mark_read: bool = False,
) -> Message:
    msg = Message(match_id=match_id, from_user_id=from_user_id, content=content)
    if mark_read:
        msg.read_at = func.now()
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    messages_total.inc()

    # MQ event only for ranking recalculation (dialog initiation score).
    # Message forwarding is done directly by the bot handler — chat must be instant.
    publish(
        "message.created",
        {
            "match_id": match_id,
            "from_user_id": from_user_id,
        },
    )

    return msg


async def count_unread_from_sender(
    session: AsyncSession,
    match_id: int,
    from_user_id: int,
) -> int:
    """Count unread messages in match from a specific sender."""
    result = await session.execute(
        select(func.count(Message.id)).where(
            Message.match_id == match_id,
            Message.from_user_id == from_user_id,
            Message.read_at.is_(None),
        )
    )
    return int(result.scalar_one() or 0)


async def mark_match_read(
    session: AsyncSession,
    match_id: int,
    reader_user_id: int,
) -> int:
    """Mark all messages in match not authored by reader as read. Returns affected rows."""
    result = await session.execute(
        update(Message)
        .where(
            Message.match_id == match_id,
            Message.from_user_id != reader_user_id,
            Message.read_at.is_(None),
        )
        .values(read_at=func.now())
    )
    await session.commit()
    return result.rowcount or 0


async def get_unread_match_ids(
    session: AsyncSession, user_id: int
) -> set[int]:
    """Match ids (for matches user participates in) with unread messages from partner."""
    result = await session.execute(
        select(Message.match_id)
        .join(Match, Match.id == Message.match_id)
        .where(
            ((Match.user1_id == user_id) | (Match.user2_id == user_id)),
            Message.from_user_id != user_id,
            Message.read_at.is_(None),
        )
        .distinct()
    )
    return {row[0] for row in result.all()}


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
