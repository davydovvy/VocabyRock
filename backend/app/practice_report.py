"""Parent-only exercise history aggregated by the session's start day."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Pack, PracticeSession, User, Word

PAGE_SIZE = 20


def report(
    db: Session,
    start: date,
    end: date,
    tz: str,
    child_id: int | None,
    kind: str | None,
    page: int = 1,
):
    if page < 1:
        raise HTTPException(400, "Choose a valid page")
    if end < start or end == date.max:
        raise HTTPException(400, "Choose a valid date range")
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(400, "Choose a valid timezone") from None
    if child_id is not None:
        child = db.get(User, child_id)
        if not child or child.role != "child":
            raise HTTPException(400, "Choose a child")
    if kind is not None and kind not in {"match", "flashcard", "choice", "type", "listen"}:
        raise HTTPException(400, "Choose a valid exercise")

    from_utc = datetime.combine(start, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
    until_utc = (
        datetime.combine(end + timedelta(days=1), time.min, zone)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    query = select(PracticeSession).where(
        PracticeSession.started_at >= from_utc, PracticeSession.started_at < until_utc
    )
    if child_id is not None:
        query = query.where(PracticeSession.user_id == child_id)
    if kind is not None:
        query = query.where(PracticeSession.kind == kind)
    sessions = db.scalars(
        query.order_by(
            PracticeSession.started_at.desc(), PracticeSession.id.desc()
        ).execution_options(yield_per=100)
    )
    users = {u.id: u.name for u in db.scalars(select(User).where(User.role == "child"))}
    packs = {p.id: p.name for p in db.scalars(select(Pack))}
    words = {w.id: w.english for w in db.scalars(select(Word))}
    daily = defaultdict(lambda: {"started": 0, "completed": 0})
    by_pack = defaultdict(lambda: {"started": 0, "completed": 0})
    by_word = defaultdict(lambda: {"attempts": 0, "correct": 0, "incorrect": 0})
    details = []
    total_attempts = correct_attempts = session_count = completed_count = 0
    for session in sessions:
        session_count += 1
        include_details = (page - 1) * PAGE_SIZE <= session_count - 1 < page * PAGE_SIZE
        day = session.started_at.replace(tzinfo=timezone.utc).astimezone(zone).date().isoformat()
        pack_name = session.pack_name or packs.get(session.pack_id) or "All words"
        daily[day]["started"] += 1
        by_pack[(day, pack_name)]["started"] += 1
        if session.finished_at:
            completed_count += 1
            daily[day]["completed"] += 1
            by_pack[(day, pack_name)]["completed"] += 1
        history = session.attempt_history or session.results or []
        attempts = []
        answered_indices = set()
        for item in history:
            index = item.get("index", -1)
            if include_details:
                answered_indices.add(index)
            task = session.tasks[index] if 0 <= index < len(session.tasks) else {}
            word_id = item.get("word_id") or task.get("word_id")
            correct = bool(item.get("correct"))
            total_attempts += 1
            correct_attempts += int(correct)
            word_key = (
                word_id,
                words.get(word_id) or task.get("english") or task.get("prompt") or "Deleted word",
            )
            by_word[word_key]["attempts"] += 1
            by_word[word_key]["correct" if correct else "incorrect"] += 1
            if include_details:
                attempts.append(
                    {
                        "index": index,
                        "word_id": word_id,
                        "word": word_key[1],
                        "prompt": task.get("prompt") or task.get("english") or "Audio question",
                        "correct": correct,
                        "chosen": item.get("chosen"),
                        "answer": item.get("answer") or task.get("accepted") or task.get("answer"),
                        "answered_at": item.get("answered_at"),
                        "assisted": bool(item.get("assisted")),
                        "hint_used": bool(item.get("hint_used")),
                    }
                )
        if not include_details:
            continue
        for index, task in enumerate(session.tasks):
            if index in answered_indices:
                continue
            word_id = task.get("word_id")
            attempts.append(
                {
                    "index": index,
                    "word_id": word_id,
                    "word": words.get(word_id)
                    or task.get("english")
                    or task.get("prompt")
                    or "Deleted word",
                    "prompt": task.get("prompt") or task.get("english") or "Audio question",
                    "correct": None,
                    "chosen": None,
                    "answer": task.get("accepted") or task.get("answer"),
                    "answered_at": None,
                    "assisted": False,
                    "hint_used": False,
                }
            )
        details.append(
            {
                "id": session.id,
                "child_id": session.user_id,
                "child": users.get(session.user_id, "Deleted child"),
                "pack_id": session.pack_id,
                "pack": pack_name,
                "kind": session.kind,
                "mode": session.mode,
                "direction": session.direction,
                "started_at": session.started_at.isoformat() + "Z",
                "finished_at": session.finished_at.isoformat() + "Z"
                if session.finished_at
                else None,
                "question_count": len(session.tasks),
                "answered_count": len(session.results or []),
                "correct_count": (
                    sum(bool(task.get("locked")) for task in session.tasks)
                    if session.kind == "match" and session.tasks[0].get("big_match")
                    else sum(bool(r.get("correct")) for r in (session.results or []))
                ),
                "attempts": attempts,
            }
        )
    return {
        "summary": {
            "started": session_count,
            "completed": completed_count,
            "attempts": total_attempts,
            "correct": correct_attempts,
        },
        "daily": [{"date": day, **counts} for day, counts in sorted(daily.items())],
        "packs": [
            {"date": day, "pack": pack, **counts} for (day, pack), counts in sorted(by_pack.items())
        ],
        "difficult_words": [
            {"word_id": word_id, "word": word, **counts}
            for (word_id, word), counts in sorted(
                by_word.items(),
                key=lambda row: (-row[1]["incorrect"], -row[1]["attempts"], row[0][1]),
            )
            if counts["incorrect"]
        ],
        "sessions": details,
        "pagination": {
            "page": page,
            "page_size": PAGE_SIZE,
            "total_sessions": session_count,
            "total_pages": max(1, (session_count + PAGE_SIZE - 1) // PAGE_SIZE),
        },
    }
