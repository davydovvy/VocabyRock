"""Durable, serial pronunciation downloads for the word library."""

import asyncio
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from . import wiktapi
from .config import get_settings
from .db import SessionLocal
from .models import Word, now

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
SUCCESS_COOLDOWN_SECONDS = 15
_cooldown_until = None
_rate_limit_streak = 0
RATE_LIMIT_ERROR = "Wikimedia is limiting downloads; retry scheduled."
EXHAUSTED_RATE_LIMIT_ERROR = "Wikimedia kept limiting downloads. Retry when ready."


def queue_audio(word: Word, url: str) -> None:
    wiktapi.validate_audio_url(url)
    word.audio_source_url = url
    word.audio_status = "pending"
    word.audio_attempts = 0
    word.audio_next_attempt_at = max(now(), _cooldown_until) if _cooldown_until else now()
    word.audio_error = None


async def process_due(session_factory=SessionLocal) -> bool:
    """Process at most one due word, allowing one downloader request at a time."""
    global _cooldown_until, _rate_limit_streak
    if not get_settings().audio_downloads_enabled:
        return False
    current = now()
    if _cooldown_until and current < _cooldown_until:
        return False
    with session_factory() as db:
        word = db.scalar(
            select(Word)
            .where(
                Word.audio_status.in_(["pending", "retrying"]),
                Word.audio_next_attempt_at <= current,
            )
            .order_by(Word.audio_next_attempt_at, Word.id)
            .limit(1)
        )
        if not word:
            return False
        word_id, url = word.id, word.audio_source_url
    if not url:
        return False

    try:
        local_path = await wiktapi.save_audio(url)
    except wiktapi.AudioRateLimited as exc:
        _rate_limit_streak = min(MAX_ATTEMPTS, _rate_limit_streak + 1)
        delay = max(exc.retry_after, min(1800, 30 * 2 ** (_rate_limit_streak - 1)))
        _cooldown_until = now() + timedelta(seconds=delay)
        with session_factory() as db:
            word = db.get(Word, word_id)
            if word and word.audio_source_url == url:
                word.audio_status = "retrying"
                word.audio_attempts = 0
                word.audio_next_attempt_at = _cooldown_until + timedelta(seconds=1)
                word.audio_error = RATE_LIMIT_ERROR
                logger.info("Wikimedia limited word %s; retry in %s seconds", word_id, delay)
                for queued in db.scalars(
                    select(Word).where(Word.audio_status.in_(["pending", "retrying"]))
                ):
                    if (
                        not queued.audio_next_attempt_at
                        or queued.audio_next_attempt_at < _cooldown_until
                    ):
                        queued.audio_next_attempt_at = _cooldown_until
                    if queued.id != word_id and queued.audio_error is None:
                        queued.audio_error = RATE_LIMIT_ERROR
                db.commit()
        return True
    except (HTTPException, OSError) as exc:
        _rate_limit_streak = 0
        with session_factory() as db:
            word = db.get(Word, word_id)
            if word and word.audio_source_url == url:
                if word.audio_error == RATE_LIMIT_ERROR:
                    word.audio_attempts = 0
                word.audio_attempts += 1
                word.audio_error = str(exc.detail if isinstance(exc, HTTPException) else exc)[:255]
                if word.audio_attempts >= MAX_ATTEMPTS:
                    word.audio_status = "failed"
                    word.audio_next_attempt_at = None
                    logger.warning(
                        "Pronunciation download failed for word %s: %s", word_id, word.audio_error
                    )
                else:
                    word.audio_status = "retrying"
                    word.audio_next_attempt_at = now() + timedelta(
                        seconds=min(1800, 30 * 2 ** (word.audio_attempts - 1))
                    )
                db.commit()
        return True

    with session_factory() as db:
        word = db.get(Word, word_id)
        if not word or word.audio_source_url != url:
            wiktapi.remove_audio(local_path)
            return True
        old_path = word.audio
        word.audio = local_path
        word.audio_status = "ready"
        word.audio_next_attempt_at = None
        word.audio_error = None
        try:
            db.commit()
        except Exception:
            db.rollback()
            wiktapi.remove_audio(local_path)
            raise
    wiktapi.remove_audio(old_path)
    logger.info("Pronunciation saved for word %s", word_id)
    _rate_limit_streak = 0
    _cooldown_until = now() + timedelta(seconds=SUCCESS_COOLDOWN_SECONDS)
    return True


def recover_rate_limited_failures(session_factory=SessionLocal) -> int:
    """Put words failed under the old rate-limit policy back into the queue."""
    global _cooldown_until
    with session_factory() as db:
        words = db.scalars(
            select(Word).where(
                Word.audio_status == "failed",
                Word.audio_error == EXHAUSTED_RATE_LIMIT_ERROR,
                Word.audio_source_url.is_not(None),
            )
        ).all()
        next_due = db.scalar(
            select(Word.audio_next_attempt_at)
            .where(Word.audio_status.in_(["pending", "retrying"]))
            .order_by(Word.audio_next_attempt_at.desc())
            .limit(1)
        )
        for word in words:
            word.audio_status = "retrying"
            word.audio_attempts = 0
            word.audio_next_attempt_at = max(now(), next_due) if next_due else now()
            word.audio_error = RATE_LIMIT_ERROR
        rate_limit_due = db.scalar(
            select(Word.audio_next_attempt_at)
            .where(
                Word.audio_status.in_(["pending", "retrying"]),
                Word.audio_error == RATE_LIMIT_ERROR,
            )
            .order_by(Word.audio_next_attempt_at.desc())
            .limit(1)
        )
        if rate_limit_due and rate_limit_due > now():
            _cooldown_until = rate_limit_due
            for pending in db.scalars(
                select(Word).where(
                    Word.audio_status == "pending",
                    Word.audio_error.is_(None),
                    Word.audio_next_attempt_at >= rate_limit_due,
                )
            ):
                pending.audio_error = RATE_LIMIT_ERROR
        db.commit()
        if words:
            logger.info("Restored %s pronunciation downloads after rate limiting", len(words))
        return len(words)


async def run_worker() -> None:
    try:
        recover_rate_limited_failures()
    except Exception:
        logger.exception("Could not restore pronunciation queue after restart")
    while True:
        try:
            await process_due()
        except Exception:
            logger.exception("Pronunciation worker failed")
        await asyncio.sleep(3)
