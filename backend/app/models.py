from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    avatar: Mapped[str] = mapped_column(String(32))
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    stars: Mapped[int] = mapped_column(Integer, default=0)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    user: Mapped[User] = relationship()


class Word(Base):
    __tablename__ = "words"
    id: Mapped[int] = mapped_column(primary_key=True)
    english: Mapped[str] = mapped_column(String(160), index=True)
    translations: Mapped[list] = mapped_column(JSON)
    ipa: Mapped[str | None] = mapped_column(String(120), nullable=True)
    part_of_speech: Mapped[str | None] = mapped_column(String(60), nullable=True)
    picture: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    example_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Pack(Base):
    __tablename__ = "packs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cover: Mapped[str | None] = mapped_column(String(255), nullable=True)
    words: Mapped[list["PackWord"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan", order_by="PackWord.position"
    )


class PackWord(Base):
    __tablename__ = "pack_words"
    __table_args__ = (UniqueConstraint("pack_id", "word_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id", ondelete="CASCADE"))
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    pack: Mapped[Pack] = relationship(back_populates="words")
    word: Mapped[Word] = relationship()


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "word_id", "direction"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"))
    direction: Mapped[str] = mapped_column(String(8))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    incorrect: Mapped[int] = mapped_column(Integer, default=0)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="new")
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pack_id: Mapped[int | None] = mapped_column(
        ForeignKey("packs.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(8))
    tasks: Mapped[list] = mapped_column(JSON)
    results: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_length: Mapped[int] = mapped_column(Integer, default=10)
    accent: Mapped[str] = mapped_column(String(8), default="en-US")
    direction: Mapped[str] = mapped_column(String(8), default="en-ru")
    fold_yo: Mapped[bool] = mapped_column(Boolean, default=True)
    lenient_typos: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_exercises: Mapped[list] = mapped_column(
        JSON, default=lambda: ["match", "flashcard", "choice", "type", "listen"]
    )
    child_avatar_change: Mapped[bool] = mapped_column(Boolean, default=True)
