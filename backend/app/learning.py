import random
import re
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSettings, PackWord, PracticeSession, Progress, User, Word, now


def normalize(value: str, fold_yo: bool = True) -> str:
    value = " ".join(value.casefold().strip().split())
    value = re.sub(r"[.!?]+$", "", value)
    return value.replace("ё", "е") if fold_yo else value


def one_typo(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if left == right:
        return True
    if len(left) > len(right):
        left, right = right, left
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    return any(left == right[:i] + right[i + 1 :] for i in range(len(right)))


def check_text(answer: str, accepted: list[str], settings: AppSettings) -> bool:
    actual = normalize(answer, settings.fold_yo)
    return any(
        actual == normalize(item, settings.fold_yo)
        or (settings.lenient_typos and one_typo(actual, normalize(item, settings.fold_yo)))
        for item in accepted
    )


def update_progress(
    db: Session,
    user_id: int,
    word_id: int,
    direction: str,
    correct: bool,
    rating: str | None = None,
):
    progress = db.scalar(
        select(Progress).where(
            Progress.user_id == user_id,
            Progress.word_id == word_id,
            Progress.direction == direction,
        )
    )
    if not progress:
        progress = Progress(
            user_id=user_id,
            word_id=word_id,
            direction=direction,
            attempts=0,
            correct=0,
            incorrect=0,
            interval_days=0,
            status="new",
        )
        db.add(progress)
    progress.attempts += 1
    progress.last_practiced_at = now()
    if correct:
        progress.correct += 1
        if rating == "hard":
            progress.interval_days = 1
        elif progress.interval_days == 0:
            progress.interval_days = 1
        else:
            progress.interval_days = min(90, max(2, round(progress.interval_days * 2.2)))
        progress.next_review_at = now() + timedelta(days=progress.interval_days)
        progress.status = (
            "mastered"
            if progress.interval_days >= 10
            else "review"
            if progress.interval_days >= 2
            else "learning"
        )
    else:
        progress.incorrect += 1
        progress.interval_days = 0
        progress.next_review_at = now() + timedelta(hours=4)
        progress.status = "learning"
    return progress


def _select_words(
    db: Session,
    user: User,
    pack_id: int | None,
    mode: str,
    direction: str,
    limit: int,
    word_ids: list[int] | None,
):
    query = select(Word)
    if pack_id is not None:
        query = query.join(PackWord).where(PackWord.pack_id == pack_id)
    if word_ids is not None:
        query = query.where(Word.id.in_(word_ids))
    words = db.scalars(query).unique().all()
    progress = {
        p.word_id: p
        for p in db.scalars(
            select(Progress).where(Progress.user_id == user.id, Progress.direction == direction)
        )
    }

    def eligible(word):
        p = progress.get(word.id)
        if mode == "new":
            return p is None
        if mode in ("hard", "mistakes"):
            return (
                p is not None
                and p.incorrect > 0
                and (mode == "mistakes" or p.incorrect >= p.correct)
            )
        if mode == "practice":
            return p is not None and (p.next_review_at is None or p.next_review_at <= now())
        return True

    words = [word for word in words if eligible(word)]
    random.shuffle(words)
    words.sort(
        key=lambda word: (
            0
            if word.id not in progress
            else 1
            if progress[word.id].next_review_at and progress[word.id].next_review_at <= now()
            else 2
            if progress[word.id].status == "learning"
            else 3
        )
    )
    return words[:limit], db.scalars(select(Word)).all()


def _unique_candidates(words: list[Word], direction: str) -> list[Word]:
    seen_en, seen_ru = set(), set()
    result = []
    for word in words:
        en = normalize(word.english)
        ru = {normalize(x) for x in word.translations}
        if en in seen_en or ru & seen_ru:
            continue
        seen_en.add(en)
        seen_ru.update(ru)
        result.append(word)
    return result


def _can_ask_unambiguously(word: Word, library: list[Word], direction: str, kind: str) -> bool:
    same_english = any(
        other.id != word.id and normalize(other.english) == normalize(word.english)
        for other in library
    )
    if kind == "listen":
        # Audio contains only the English word, so it cannot identify a particular homonym.
        return not same_english
    if direction == "en-ru":
        return not same_english or bool(word.example_en)
    translations = {normalize(value) for value in word.translations}
    same_russian = any(
        other.id != word.id
        and translations.intersection(normalize(value) for value in other.translations)
        for other in library
    )
    return not same_russian or bool(word.example_ru)


def create_practice(
    db: Session,
    user: User,
    pack_id: int | None,
    mode: str,
    kind: str,
    direction: str,
    length: int,
    word_ids: list[int] | None = None,
):
    settings = db.get(AppSettings, 1)
    if kind not in settings.allowed_exercises:
        raise HTTPException(400, "This game is turned off")
    selected, library = _select_words(db, user, pack_id, mode, direction, length * 4, word_ids)
    selected = [
        word for word in selected if _can_ask_unambiguously(word, library, direction, kind)
    ][:length]
    if kind in ("match", "choice", "listen") and (kind != "listen" or direction == "en-ru"):
        selected = _unique_candidates(selected, direction)
    if kind == "match":
        selected = selected[:5]
    if not selected:
        raise HTTPException(400, "No words are ready. Try another mode or pack")
    tasks = []
    if kind == "match":
        for word in selected:
            prompt = word.english if direction == "en-ru" else word.translations[0]
            hint = word.example_en if direction == "en-ru" else word.example_ru
            tasks.append(
                {
                    "word_id": word.id,
                    "prompt": f"{prompt} · {hint}" if hint else prompt,
                    "answer": word.translations[0] if direction == "en-ru" else word.english,
                    "token": secrets.randbelow(900000) + 100000,
                }
            )
    else:
        for word in selected:
            prompt = word.english if direction == "en-ru" else word.translations[0]
            accepted = word.translations if direction == "en-ru" else [word.english]
            task = {
                "word_id": word.id,
                "prompt": prompt,
                "accepted": accepted,
                "english": word.english,
                "picture": word.picture,
                "ipa": word.ipa,
                "hint": word.example_en if direction == "en-ru" else word.example_ru,
            }
            if kind == "listen":
                task["prompt"] = None
                task["accepted"] = word.translations if direction == "en-ru" else [word.english]
            if kind == "choice" or (kind == "listen" and direction == "en-ru"):
                candidates = _unique_candidates(
                    [word] + random.sample(library, len(library)), direction
                )
                distractors = [w for w in candidates if w.id != word.id][:3]
                options = [(word.id, accepted[0])] + [
                    (w.id, w.translations[0] if direction == "en-ru" else w.english)
                    for w in distractors
                ]
                random.shuffle(options)
                task["options"] = [
                    {"token": secrets.randbelow(10**9), "text": label, "word_id": wid}
                    for wid, label in options
                ]
            tasks.append(task)
    practice = PracticeSession(
        user_id=user.id,
        pack_id=pack_id,
        mode=mode,
        kind=kind,
        direction=direction,
        tasks=tasks,
        results=[],
    )
    db.add(practice)
    db.commit()
    db.refresh(practice)
    return practice


def public_session(practice: PracticeSession):
    tasks = []
    for task in practice.tasks:
        public = {
            key: value
            for key, value in task.items()
            if key not in {"word_id", "accepted", "answer", "token", "english"}
        }
        if practice.kind == "match":
            public["prompt"] = task["prompt"]
        if practice.kind == "listen":
            public["speech"] = task["english"]
        if practice.kind == "flashcard" and any(r["index"] == len(tasks) for r in practice.results):
            public["answer"] = task["accepted"]
        if "options" in public:
            public["options"] = [
                {"token": x["token"], "text": x["text"]} for x in public["options"]
            ]
        tasks.append(public)
    result = {
        "id": practice.id,
        "kind": practice.kind,
        "mode": practice.mode,
        "direction": practice.direction,
        "tasks": tasks,
        "results": practice.results,
        "finished": practice.finished_at is not None,
    }
    if practice.kind == "match":
        options = [{"token": task["token"], "text": task["answer"]} for task in practice.tasks]
        random.Random(practice.id).shuffle(options)
        result["match_options"] = options
    return result


def submit_answer(
    db: Session,
    practice: PracticeSession,
    index: int,
    answer: str | None,
    option_id: int | None,
    rating: str | None,
):
    if practice.finished_at:
        raise HTTPException(400, "This game is finished")
    if index >= len(practice.tasks) or any(r["index"] == index for r in practice.results):
        raise HTTPException(400, "This question is not available")
    task = practice.tasks[index]
    settings = db.get(AppSettings, 1)
    if practice.kind == "match":
        correct = option_id == task["token"]
        if not correct:
            return {"correct": False, "retry": True, "message": "Try again!"}
    elif practice.kind == "flashcard":
        if rating is None:
            raise HTTPException(400, "Pick how well you knew it")
        correct = rating != "again"
    elif practice.kind in ("choice", "listen") and task.get("options"):
        correct = any(
            o["token"] == option_id and o["word_id"] == task["word_id"] for o in task["options"]
        )
    else:
        correct = check_text(answer or "", task["accepted"], settings)
    result = {
        "index": index,
        "correct": correct,
        "answer": task.get("answer") or task.get("accepted", []),
        "word_id": task["word_id"],
    }
    results = list(practice.results)
    results.append(result)
    practice.results = results
    update_progress(db, practice.user_id, task["word_id"], practice.direction, correct, rating)
    if len(results) == len(practice.tasks):
        practice.finished_at = now()
        user = db.get(User, practice.user_id)
        earned = sum(5 if r["correct"] else 1 for r in results)
        user.xp += earned
        user.stars += max(1, sum(r["correct"] for r in results) // 3)
    db.commit()
    return {
        "correct": correct,
        "retry": False,
        "answer": result["answer"],
        "finished": practice.finished_at is not None,
        "correct_count": sum(r["correct"] for r in results),
        "total": len(practice.tasks),
    }
