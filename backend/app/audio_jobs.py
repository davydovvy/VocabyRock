"""Durable, serial pronunciation downloads for the word library."""

import asyncio
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from . import wiktapi
from .db import SessionLocal
from .models import Word, now

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
_cooldown_until = None


def queue_audio(word: Word, url: str) -> None:
    wiktapi.validate_audio_url(url)
    word.audio_source_url = url
    word.audio_status = "pending"
    word.audio_attempts = 0
    word.audio_next_attempt_at = max(now(), _cooldown_until) if _cooldown_until else now()
    word.audio_error = None


async def process_due(session_factory=SessionLocal) -> bool:
    """Process at most one due word, allowing one downloader request at a time."""
    global _cooldown_until
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
        with session_factory() as db:
            word = db.get(Word, word_id)
            if word and word.audio_source_url == url:
                word.audio_attempts += 1
                delay = max(exc.retry_after, min(1800, 30 * 2 ** (word.audio_attempts - 1)))
                _cooldown_until = now() + timedelta(seconds=delay)
                if word.audio_attempts >= MAX_ATTEMPTS:
                    word.audio_status = "failed"
                    word.audio_next_attempt_at = None
                    word.audio_error = "Wikimedia kept limiting downloads. Retry when ready."
                    logger.warning("Pronunciation download exhausted retries for word %s", word_id)
                else:
                    word.audio_status = "retrying"
                    word.audio_next_attempt_at = _cooldown_until
                    word.audio_error = "Wikimedia is limiting downloads; retry scheduled."
                    logger.info("Wikimedia limited word %s; retry in %s seconds", word_id, delay)
                for queued in db.scalars(
                    select(Word).where(Word.audio_status.in_(["pending", "retrying"]))
                ):
                    if (
                        not queued.audio_next_attempt_at
                        or queued.audio_next_attempt_at < _cooldown_until
                    ):
                        queued.audio_next_attempt_at = _cooldown_until
                db.commit()
        return True
    except (HTTPException, OSError) as exc:
        with session_factory() as db:
            word = db.get(Word, word_id)
            if word and word.audio_source_url == url:
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
    _cooldown_until = now() + timedelta(seconds=5)
    return True


async def run_worker() -> None:
    while True:
        try:
            await process_due()
        except Exception:
            logger.exception("Pronunciation worker failed")
        await asyncio.sleep(3)
