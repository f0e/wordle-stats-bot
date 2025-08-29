from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.sql import func

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class GuildUserStats(Base):
    __tablename__ = "guild_user_stats"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationship to plays
    plays: Mapped[list[WordlePlay]] = relationship("WordlePlay", back_populates="user")


class WordlePlay(Base):
    __tablename__ = "wordle_play"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    stats_discord_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    guesses: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # none if failed
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "guild_id",
            "discord_user_id",
            "stats_discord_message_id",
            name="_user_message_uc",
        ),
        ForeignKeyConstraint(
            ["guild_id", "discord_user_id"],
            ["guild_user_stats.guild_id", "guild_user_stats.discord_user_id"],
            ondelete="CASCADE",
        ),
        Index("ix_wordleplay_guild_user", "guild_id", "discord_user_id"),
    )

    # relationship back to user
    user: Mapped[GuildUserStats] = relationship(
        "GuildUserStats", back_populates="plays"
    )


engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
