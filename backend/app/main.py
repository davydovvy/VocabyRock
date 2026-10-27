import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import String, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import (
    child,
    clear_failed_logins,
    create_session,
    current_user,
    login_allowed,
    logout,
    parent,
    record_failed_login,
    verify_password,
)
from . import audio_jobs, pixabay, wiktapi
from .config import get_settings
from .csv_io import HEADERS, export_csv, import_csv, preview_csv
from .db import get_db
from .learning import create_practice, public_session, submit_answer
from .media import remove_picture, save_picture, save_picture_data
from .models import AppSettings, Pack, PackWord, PracticeSession, Progress, User, Word, now
from .schemas import (
    AnswerInput,
    PackInput,
    PixabaySelection,
    ProfileInput,
    ResetInput,
    SessionStart,
    SettingsInput,
    WordSaveInput,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = asyncio.create_task(audio_jobs.run_worker())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(
    title="VacabyRock", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan
)
AVATARS = ["fox", "bear", "rabbit", "cat", "dog", "owl", "panda", "koala"]


def require_word(db: Session, word_id: int) -> Word:
    word = db.get(Word, word_id)
    if not word:
        raise HTTPException(404, "Word not found")
    return word


def require_pack(db: Session, pack_id: int) -> Pack:
    pack = db.get(Pack, pack_id)
    if not pack:
        raise HTTPException(404, "Pack not found")
    return pack


def pack_data(pack: Pack, db: Session, user: User | None = None):
    ids = [item.word_id for item in pack.words]
    learned = 0
    if user and user.role == "child" and ids:
        learned = (
            db.scalar(
                select(func.count(Progress.id)).where(
                    Progress.user_id == user.id,
                    Progress.word_id.in_(ids),
                    Progress.direction == db.get(AppSettings, 1).direction,
                    Progress.status.in_(["review", "mastered"]),
                )
            )
            or 0
        )
    return {
        "id": pack.id,
        "name": pack.name,
        "description": pack.description,
        "category": pack.category,
        "cover": pack.cover,
        "word_ids": ids,
        "word_count": len(ids),
        "learned_count": learned,
    }


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "app": "VacabyRock"}


@app.get("/api/profiles")
def profiles(db: Session = Depends(get_db)):
    return [
        {"id": u.id, "name": u.name, "avatar": u.avatar, "role": u.role}
        for u in db.scalars(select(User).order_by(User.id))
    ]


@app.post("/api/auth/child")
def login_child(body: dict, response: Response, db: Session = Depends(get_db)):
    user = db.get(User, body.get("user_id"))
    if not user or user.role != "child":
        raise HTTPException(400, "Choose a child avatar")
    create_session(db, response, user)
    return user


@app.post("/api/auth/parent")
def login_parent(body: dict, request: Request, response: Response, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "unknown"
    if not login_allowed(key):
        raise HTTPException(429, "Too many tries. Wait five minutes")
    if not verify_password(str(body.get("password", ""))):
        record_failed_login(key)
        raise HTTPException(401, "Wrong password")
    clear_failed_logins(key)
    user = db.scalar(select(User).where(User.role == "parent"))
    create_session(db, response, user)
    return user


@app.post("/api/auth/logout")
def sign_out(request: Request, response: Response, db: Session = Depends(get_db)):
    logout(request, response, db)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user


@app.get("/api/config")
def public_config(db: Session = Depends(get_db), user: User = Depends(current_user)):
    settings = db.get(AppSettings, 1)
    return {
        "accent": settings.accent,
        "direction": settings.direction,
        "session_length": settings.session_length,
        "allowed_exercises": settings.allowed_exercises,
        "child_avatar_change": settings.child_avatar_change,
        "avatars": AVATARS,
    }


@app.patch("/api/profiles/{user_id}")
def update_profile(
    user_id: int,
    body: ProfileInput,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Profile not found")
    settings = db.get(AppSettings, 1)
    if user.role != "parent" and (
        user.id != target.id
        or body.name is not None
        or (body.avatar is not None and not settings.child_avatar_change)
    ):
        raise HTTPException(403, "Parent access required")
    if body.avatar is not None and body.avatar not in AVATARS:
        raise HTTPException(400, "Choose an available avatar")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(target, key, value)
    db.commit()
    db.refresh(target)
    return target


@app.get("/api/words")
def list_words(
    q: str = "",
    pack_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = select(Word).order_by(Word.english, Word.id)
    if pack_id is not None:
        query = query.join(PackWord).where(PackWord.pack_id == pack_id)
    if q:
        query = query.where(
            or_(Word.english.ilike(f"%{q}%"), Word.translations.cast(String).ilike(f"%{q}%"))
        )
    return db.scalars(query).unique().all()


@app.post("/api/words", status_code=201)
def add_word(body: WordSaveInput, db: Session = Depends(get_db), _: User = Depends(parent)):
    fields = body.model_dump(exclude={"audio_url"})
    word = Word(**fields)
    if body.audio_url:
        audio_jobs.queue_audio(word, body.audio_url)
    db.add(word)
    db.commit()
    db.refresh(word)
    return word


@app.get("/api/words/{word_id}")
def get_word(word_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return require_word(db, word_id)


@app.put("/api/words/{word_id}")
def edit_word(
    word_id: int, body: WordSaveInput, db: Session = Depends(get_db), _: User = Depends(parent)
):
    word = require_word(db, word_id)
    for key, value in body.model_dump(exclude={"audio_url"}).items():
        setattr(word, key, value)
    if body.audio_url:
        audio_jobs.queue_audio(word, body.audio_url)
    db.commit()
    db.refresh(word)
    return word


@app.post("/api/words/{word_id}/audio/retry")
def retry_word_audio(word_id: int, db: Session = Depends(get_db), _: User = Depends(parent)):
    word = require_word(db, word_id)
    if word.audio_status != "failed" or not word.audio_source_url:
        raise HTTPException(409, "This word has no failed pronunciation download.")
    audio_jobs.queue_audio(word, word.audio_source_url)
    db.commit()
    db.refresh(word)
    return word


@app.delete("/api/words/{word_id}")
def delete_word(word_id: int, db: Session = Depends(get_db), _: User = Depends(parent)):
    word = require_word(db, word_id)
    picture = word.picture
    audio_path = word.audio
    db.execute(delete(PackWord).where(PackWord.word_id == word_id))
    db.execute(delete(Progress).where(Progress.word_id == word_id))
    db.delete(word)
    db.commit()
    remove_picture(picture)
    wiktapi.remove_audio(audio_path)
    return {"ok": True}


@app.get("/api/dictionary")
async def dictionary_lookup(word: str = "", _: User = Depends(parent)):
    return await wiktapi.lookup(word)


@app.post("/api/words/{word_id}/picture")
async def upload_word_picture(
    word_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(parent),
):
    word = require_word(db, word_id)
    path = await save_picture(file)
    remove_picture(word.picture)
    word.picture = path
    db.commit()
    return {"picture": path}


@app.get("/api/pixabay/search")
async def search_pixabay(q: str = "", _: User = Depends(parent)):
    return await pixabay.search_images(q)


@app.post("/api/words/{word_id}/pixabay")
async def set_pixabay_picture(
    word_id: int,
    body: PixabaySelection,
    db: Session = Depends(get_db),
    _: User = Depends(parent),
):
    word = require_word(db, word_id)
    url = await pixabay.picture_url(body.image_id)
    path = save_picture_data(await pixabay.download_image(url))
    old_picture = word.picture
    word.picture = path
    try:
        db.commit()
    except Exception:
        db.rollback()
        remove_picture(path)
        raise
    remove_picture(old_picture)
    return {"picture": path}


@app.get("/api/packs")
def list_packs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [pack_data(pack, db, user) for pack in db.scalars(select(Pack).order_by(Pack.id))]


@app.post("/api/packs", status_code=201)
def add_pack(body: PackInput, db: Session = Depends(get_db), _: User = Depends(parent)):
    pack = Pack(**body.model_dump())
    db.add(pack)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A pack with this name already exists")
    db.refresh(pack)
    return pack_data(pack, db)


@app.get("/api/packs/{pack_id}")
def get_pack(pack_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return pack_data(require_pack(db, pack_id), db, user)


@app.put("/api/packs/{pack_id}")
def edit_pack(
    pack_id: int, body: PackInput, db: Session = Depends(get_db), _: User = Depends(parent)
):
    pack = require_pack(db, pack_id)
    for key, value in body.model_dump().items():
        setattr(pack, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A pack with this name already exists")
    return pack_data(pack, db)


@app.delete("/api/packs/{pack_id}")
def delete_pack(pack_id: int, db: Session = Depends(get_db), _: User = Depends(parent)):
    pack = require_pack(db, pack_id)
    remove_picture(pack.cover)
    db.delete(pack)
    db.commit()
    return {"ok": True}


@app.put("/api/packs/{pack_id}/words")
def set_pack_words(
    pack_id: int, body: dict, db: Session = Depends(get_db), _: User = Depends(parent)
):
    pack = require_pack(db, pack_id)
    ids = body.get("word_ids", [])
    if (
        not isinstance(ids, list)
        or len(ids) != len(set(ids))
        or any(not isinstance(x, int) for x in ids)
    ):
        raise HTTPException(400, "Choose each word only once")
    found = set(db.scalars(select(Word.id).where(Word.id.in_(ids))))
    if found != set(ids):
        raise HTTPException(400, "One or more words were not found")
    pack.words.clear()
    db.flush()
    pack.words.extend(
        PackWord(word_id=word_id, position=index) for index, word_id in enumerate(ids)
    )
    db.commit()
    return pack_data(pack, db)


@app.post("/api/packs/{pack_id}/cover")
async def upload_pack_cover(
    pack_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(parent),
):
    pack = require_pack(db, pack_id)
    path = await save_picture(file)
    remove_picture(pack.cover)
    pack.cover = path
    db.commit()
    return {"cover": path}


@app.get("/api/import/template")
def csv_template(_: User = Depends(parent)):
    return PlainTextResponse(
        "\ufeff" + ",".join(HEADERS) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vacabyrock-template.csv"'},
    )


async def read_csv(file: UploadFile):
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "CSV is too large (2 MB maximum)")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Save the CSV as UTF-8") from exc


@app.post("/api/import/preview")
async def preview_import(
    file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(parent)
):
    return preview_csv(await read_csv(file), db)


@app.post("/api/import")
async def import_words(
    pack_id: int | None = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(parent),
):
    if pack_id is not None:
        require_pack(db, pack_id)
    return import_csv(await read_csv(file), db, pack_id)


@app.get("/api/export")
def export_words(
    pack_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(parent)
):
    query = select(Word)
    if pack_id is not None:
        require_pack(db, pack_id)
        query = query.join(PackWord).where(PackWord.pack_id == pack_id).order_by(PackWord.position)
    else:
        query = query.order_by(Word.id)
    return PlainTextResponse(
        export_csv(db.scalars(query).all()),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vacabyrock-words.csv"'},
    )


@app.get("/api/settings")
def get_settings_api(db: Session = Depends(get_db), _: User = Depends(parent)):
    return db.get(AppSettings, 1)


@app.put("/api/settings")
def update_settings(body: SettingsInput, db: Session = Depends(get_db), _: User = Depends(parent)):
    settings = db.get(AppSettings, 1)
    for key, value in body.model_dump().items():
        setattr(settings, key, value)
    db.commit()
    return settings


@app.post("/api/practice", status_code=201)
def start_practice(body: SessionStart, db: Session = Depends(get_db), user: User = Depends(child)):
    settings = db.get(AppSettings, 1)
    if body.pack_id is not None:
        require_pack(db, body.pack_id)
    kind = body.kind or "choice"
    direction = body.direction or settings.direction
    practice = create_practice(
        db,
        user,
        body.pack_id,
        body.mode,
        kind,
        direction,
        body.length or settings.session_length,
        body.word_ids,
    )
    return public_session(practice)


def owned_session(db: Session, session_id: int, user: User):
    practice = db.get(PracticeSession, session_id)
    if not practice or practice.user_id != user.id:
        raise HTTPException(404, "Game not found")
    return practice


@app.get("/api/practice/{session_id}")
def get_practice(session_id: int, db: Session = Depends(get_db), user: User = Depends(child)):
    return public_session(owned_session(db, session_id, user))


@app.post("/api/practice/{session_id}/reveal/{index}")
def reveal_card(
    session_id: int, index: int, db: Session = Depends(get_db), user: User = Depends(child)
):
    practice = owned_session(db, session_id, user)
    if practice.kind != "flashcard" or not 0 <= index < len(practice.tasks):
        raise HTTPException(400, "Card not found")
    return {"answers": practice.tasks[index]["accepted"]}


@app.post("/api/practice/{session_id}/answer")
def answer_question(
    session_id: int, body: AnswerInput, db: Session = Depends(get_db), user: User = Depends(child)
):
    return submit_answer(
        db,
        owned_session(db, session_id, user),
        body.index,
        body.answer,
        body.option_id,
        body.rating,
    )


@app.get("/api/progress")
def get_progress(
    child_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    target_id = child_id if user.role == "parent" and child_id else user.id
    if user.role == "child" and target_id != user.id:
        raise HTTPException(403, "You can only see your words")
    return db.scalars(select(Progress).where(Progress.user_id == target_id)).all()


@app.get("/api/stats")
def statistics(
    child_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    if user.role == "child":
        target = user
    else:
        target = db.get(User, child_id) if child_id else None
        if not target or target.role != "child":
            raise HTTPException(400, "Choose a child")
    progress = db.scalars(select(Progress).where(Progress.user_id == target.id)).all()
    sessions = db.scalars(
        select(PracticeSession)
        .where(PracticeSession.user_id == target.id)
        .order_by(PracticeSession.started_at.desc())
        .limit(12)
    ).all()
    learned = len({p.word_id for p in progress if p.status in ("review", "mastered")})
    studying = len({p.word_id for p in progress if p.status == "learning"})
    difficult = len({p.word_id for p in progress if p.incorrect > p.correct})
    due = len({p.word_id for p in progress if p.next_review_at and p.next_review_at <= now()})
    attempts = sum(p.attempts for p in progress)
    correct = sum(p.correct for p in progress)
    achievements = []
    if attempts >= 1:
        achievements.append("First Step")
    if learned >= 10:
        achievements.append("Word Explorer")
    if learned >= 25:
        achievements.append("Word Hero")
    if target.xp >= 100:
        achievements.append("Star Collector")
    return {
        "user": target,
        "learned": learned,
        "studying": studying,
        "difficult": difficult,
        "due": due,
        "success_rate": round(correct / attempts * 100) if attempts else 0,
        "attempts": attempts,
        "achievements": achievements,
        "recent_sessions": [
            {
                "id": s.id,
                "kind": s.kind,
                "mode": s.mode,
                "date": s.started_at,
                "correct": sum(r["correct"] for r in s.results),
                "total": len(s.tasks),
            }
            for s in sessions
        ],
        "upcoming_reviews": [
            {"word_id": p.word_id, "direction": p.direction, "next_review_at": p.next_review_at}
            for p in sorted(progress, key=lambda p: p.next_review_at or now())
            if p.next_review_at
        ][:20],
    }


@app.post("/api/progress/reset")
def reset_progress(body: ResetInput, db: Session = Depends(get_db), _: User = Depends(parent)):
    if not body.confirm:
        raise HTTPException(400, "Confirm the reset first")
    target = db.get(User, body.child_id)
    if not target or target.role != "child":
        raise HTTPException(400, "Choose a child")
    query = delete(Progress).where(Progress.user_id == target.id)
    if body.word_id is not None:
        query = query.where(Progress.word_id == body.word_id)
    if body.pack_id is not None:
        require_pack(db, body.pack_id)
        ids = db.scalars(select(PackWord.word_id).where(PackWord.pack_id == body.pack_id)).all()
        query = query.where(Progress.word_id.in_(ids))
    deleted = db.execute(query).rowcount
    if body.word_id is None and body.pack_id is None:
        target.xp = 0
        target.stars = 0
    db.commit()
    return {"deleted": deleted}


@app.get("/media/{name}")
def media(name: str):
    if name != Path(name).name or not name.endswith(".webp"):
        raise HTTPException(404, "Picture not found")
    path = get_settings().data_dir / "images" / name
    if not path.is_file():
        raise HTTPException(404, "Picture not found")
    return FileResponse(path, media_type="image/webp")


@app.get("/audio/{name}")
def audio(name: str):
    if name != Path(name).name or Path(name).suffix not in {".mp3", ".ogg"}:
        raise HTTPException(404, "Pronunciation not found")
    path = get_settings().data_dir / "audio" / name
    if not path.is_file():
        raise HTTPException(404, "Pronunciation not found")
    return FileResponse(path, media_type="audio/mpeg" if path.suffix == ".mp3" else "audio/ogg")


dist = get_settings().frontend_dist
if dist.is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    root = get_settings().frontend_dist.resolve()
    asset = (root / path).resolve()
    if asset.is_relative_to(root) and asset.is_file():
        return FileResponse(asset)
    index = root / "index.html"
    if index.is_file():
        return FileResponse(index)
    return PlainTextResponse("VacabyRock frontend has not been built yet", status_code=503)
