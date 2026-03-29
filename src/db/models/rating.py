from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserRating(Base):
    __tablename__ = "user_ratings"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    primary_score: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    behavior_score: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    combined_score: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
