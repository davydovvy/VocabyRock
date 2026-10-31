"""Portable vocabulary archives. Profiles and learning progress stay on the destination."""

import io
import json
import secrets
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .media import ALLOWED
from .models import Pack, PackWord, Word
from .schemas import WordInput

MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_CONTENT_BYTES = 500 * 1024 * 1024
MAX_MEDIA_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 5000


class ArchiveWord(WordInput):
    model_config = ConfigDict(extra="forbid")

    guid: UUID
    picture: str | None = None
    audio: str | None = None
    audio_source_url: str | None = None
    audio_status: str | None = None
    audio_attempts: int = 0
    audio_next_attempt_at: datetime | None = None
    audio_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ArchivePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guid: UUID
    name: str = Field(min_length=1, max_length=100)
    description: str
    category: str | None = Field(default=None, max_length=80)
    cover: str | None = None
    word_guids: list[UUID]


class ArchiveManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["vacabyrock-vocabulary"]
    version: Literal[1]
    words: list[ArchiveWord]
    packs: list[ArchivePack]


def _stored_path(url: str | None, folder: str, suffixes: set[str]) -> Path | None:
    if url is None:
        return None
    prefix = "/media/" if folder == "images" else "/audio/"
    if not url.startswith(prefix) or Path(url).name != url[len(prefix) :]:
        raise HTTPException(409, "A library media path is invalid; fix it before exporting.")
    path = get_settings().data_dir / folder / Path(url).name
    if path.suffix.lower() not in suffixes or not path.is_file():
        raise HTTPException(409, "A library media file is missing; fix it before exporting.")
    return path


def _image_entry(guid: str, role: str) -> str:
    return f"media/images/{role}-{guid}.webp"


def _audio_entry(guid: str, suffix: str) -> str:
    return f"media/audio/{guid}{suffix}"


def export_archive(db: Session) -> StreamingResponse:
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    words = []
    packs = []
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for word in db.scalars(select(Word).order_by(Word.id)):
                picture = _stored_path(word.picture, "images", {".webp"})
                audio = _stored_path(word.audio, "audio", {".mp3", ".ogg"})
                picture_entry = _image_entry(word.guid, "word") if picture else None
                audio_entry = _audio_entry(word.guid, audio.suffix) if audio else None
                if picture:
                    archive.write(picture, picture_entry)
                if audio:
                    archive.write(audio, audio_entry)
                words.append(
                    {
                        "guid": word.guid,
                        "english": word.english,
                        "translations": word.translations,
                        "ipa": word.ipa,
                        "part_of_speech": word.part_of_speech,
                        "example_en": word.example_en,
                        "example_ru": word.example_ru,
                        "notes": word.notes,
                        "picture": picture_entry,
                        "audio": audio_entry,
                        "audio_source_url": word.audio_source_url,
                        "audio_status": word.audio_status,
                        "audio_attempts": word.audio_attempts,
                        "audio_next_attempt_at": (
                            word.audio_next_attempt_at.isoformat()
                            if word.audio_next_attempt_at
                            else None
                        ),
                        "audio_error": word.audio_error,
                        "created_at": word.created_at.isoformat(),
                        "updated_at": word.updated_at.isoformat(),
                    }
                )
            for pack in db.scalars(select(Pack).order_by(Pack.id)):
                cover = _stored_path(pack.cover, "images", {".webp"})
                cover_entry = _image_entry(pack.guid, "pack") if cover else None
                if cover:
                    archive.write(cover, cover_entry)
                packs.append(
                    {
                        "guid": pack.guid,
                        "name": pack.name,
                        "description": pack.description,
                        "category": pack.category,
                        "cover": cover_entry,
                        "word_guids": [item.word.guid for item in pack.words],
                    }
                )
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": "vacabyrock-vocabulary",
                        "version": 1,
                        "words": words,
                        "packs": packs,
                    },
                    ensure_ascii=False,
                ),
            )
        output.seek(0)
    except Exception:
        output.close()
        raise

    def chunks():
        try:
            while chunk := output.read(64 * 1024):
                yield chunk
        finally:
            output.close()

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="vacabyrock-vocabulary.zip"'},
    )


def _read_archive(data: bytes) -> tuple[ArchiveManifest, dict[str, bytes]]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise HTTPException(413, "Archive is too large (200 MB maximum).")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (
                len(entries) > MAX_ENTRIES
                or len(names) != len(set(names))
                or sum(entry.file_size for entry in entries) > MAX_CONTENT_BYTES
                or any(
                    entry.is_dir()
                    or entry.file_size > MAX_MEDIA_BYTES
                    or bool(entry.flag_bits & 1)
                    or stat.S_ISLNK(entry.external_attr >> 16)
                    for entry in entries
                )
                or "manifest.json" not in names
            ):
                raise HTTPException(400, "Archive contains invalid or oversized files.")
            manifest = ArchiveManifest.model_validate_json(archive.read("manifest.json"))
            word_guids = [str(word.guid) for word in manifest.words]
            pack_guids = [str(pack.guid) for pack in manifest.packs]
            english = [word.english.casefold() for word in manifest.words]
            pack_names = [pack.name.casefold() for pack in manifest.packs]
            if (
                len(word_guids) != len(set(word_guids))
                or len(pack_guids) != len(set(pack_guids))
                or len(english) != len(set(english))
                or len(pack_names) != len(set(pack_names))
            ):
                raise HTTPException(400, "Archive contains duplicate words or packs.")
            expected = {"manifest.json"}
            known_words = set(word_guids)
            for word in manifest.words:
                guid = str(word.guid)
                if word.picture:
                    if word.picture != _image_entry(guid, "word"):
                        raise HTTPException(400, "Archive has an invalid word picture path.")
                    expected.add(word.picture)
                if word.audio:
                    if word.audio not in {
                        _audio_entry(guid, ".mp3"),
                        _audio_entry(guid, ".ogg"),
                    }:
                        raise HTTPException(400, "Archive has an invalid pronunciation path.")
                    expected.add(word.audio)
            for pack in manifest.packs:
                guid = str(pack.guid)
                if pack.cover:
                    if pack.cover != _image_entry(guid, "pack"):
                        raise HTTPException(400, "Archive has an invalid pack cover path.")
                    expected.add(pack.cover)
                referenced = [str(word_guid) for word_guid in pack.word_guids]
                if len(referenced) != len(set(referenced)) or not set(referenced) <= known_words:
                    raise HTTPException(400, "Archive pack refers to an unknown or repeated word.")
            if set(names) != expected:
                raise HTTPException(400, "Archive media files do not match its manifest.")
            media = {name: archive.read(name) for name in expected - {"manifest.json"}}
    except (zipfile.BadZipFile, ValidationError, KeyError, ValueError) as exc:
        raise HTTPException(400, "This is not a valid VacabyRock vocabulary archive.") from exc

    for name, content in media.items():
        if not content:
            raise HTTPException(400, "Archive contains an empty media file.")
        if name.startswith("media/images/"):
            try:
                image = Image.open(io.BytesIO(content))
                image.verify()
                if image.format not in ALLOWED or image.width * image.height > 25_000_000:
                    raise ValueError("Unsupported picture")
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise HTTPException(400, "Archive contains an invalid picture.") from exc
        elif name.endswith(".ogg") and not content.startswith(b"OggS"):
            raise HTTPException(400, "Archive contains an invalid Ogg recording.")
        elif name.endswith(".mp3") and not (content.startswith(b"ID3") or content[:1] == b"\xff"):
            raise HTTPException(400, "Archive contains an invalid MP3 recording.")
    return manifest, media


def inspect_archive(data: bytes) -> dict:
    manifest, _ = _read_archive(data)
    return {"words": len(manifest.words), "packs": len(manifest.packs)}


def _new_media_file(entry: str, content: bytes, created: list[Path]) -> str:
    folder = "images" if entry.startswith("media/images/") else "audio"
    suffix = Path(entry).suffix
    directory = get_settings().data_dir / folder
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}{suffix}"
    path = directory / name
    created.append(path)
    path.write_bytes(content)
    return f"/{'media' if folder == 'images' else 'audio'}/{name}"


def import_archive(data: bytes, db: Session) -> dict:
    manifest, media = _read_archive(data)
    existing_words = db.scalars(select(Word)).all()
    existing_packs = db.scalars(select(Pack)).all()
    words_by_guid = {word.guid: word for word in existing_words}
    words_by_english = {word.english.casefold(): word for word in existing_words}
    packs_by_guid = {pack.guid: pack for pack in existing_packs}
    packs_by_name = {pack.name.casefold(): pack for pack in existing_packs}
    incoming_word_guids = {str(word.guid) for word in manifest.words}
    incoming_pack_guids = {str(pack.guid) for pack in manifest.packs}
    word_matches = {}
    pack_matches = {}
    used_word_ids = set()
    used_pack_ids = set()
    for item in manifest.words:
        guid = str(item.guid)
        match = words_by_guid.get(guid) or words_by_english.get(item.english.casefold())
        if match and (
            match.id in used_word_ids or (match.guid in incoming_word_guids and match.guid != guid)
        ):
            raise HTTPException(409, "Archive word identities conflict with this library.")
        word_matches[guid] = match
        if match:
            used_word_ids.add(match.id)
    for item in manifest.packs:
        guid = str(item.guid)
        match = packs_by_guid.get(guid) or packs_by_name.get(item.name.casefold())
        if match and (
            match.id in used_pack_ids or (match.guid in incoming_pack_guids and match.guid != guid)
        ):
            raise HTTPException(409, "Archive pack identities conflict with this library.")
        pack_matches[guid] = match
        if match:
            used_pack_ids.add(match.id)

    old_media = {
        path
        for path in (
            *[word.picture for word in existing_words],
            *[word.audio for word in existing_words],
            *[pack.cover for pack in existing_packs],
        )
        if path
    }
    created = []
    try:
        media_paths = {
            entry: _new_media_file(entry, content, created) for entry, content in media.items()
        }
        db.execute(delete(PackWord))
        db.flush()
        for pack in existing_packs:
            if pack.id not in used_pack_ids:
                db.delete(pack)
            else:
                pack.name = f"__archive_import_{pack.id}_{secrets.token_hex(4)}"
        for word in existing_words:
            if word.id not in used_word_ids:
                db.delete(word)
        db.flush()
        imported_words = {}
        for item in manifest.words:
            guid = str(item.guid)
            word = word_matches[guid] or Word(guid=guid)
            fields = item.model_dump(exclude={"guid", "picture", "audio"})
            for key, value in fields.items():
                setattr(word, key, value)
            word.guid = guid
            word.picture = media_paths.get(item.picture)
            word.audio = media_paths.get(item.audio)
            db.add(word)
            imported_words[guid] = word
        db.flush()
        for item in manifest.packs:
            guid = str(item.guid)
            pack = pack_matches[guid] or Pack(guid=guid)
            pack.guid = guid
            pack.name = item.name
            pack.description = item.description
            pack.category = item.category
            pack.cover = media_paths.get(item.cover)
            db.add(pack)
            db.flush()
            for position, word_guid in enumerate(item.word_guids):
                db.add(
                    PackWord(
                        pack_id=pack.id,
                        word_id=imported_words[str(word_guid)].id,
                        position=position,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        for path in created:
            path.unlink(missing_ok=True)
        raise

    for url in old_media:
        try:
            prefix, name = url.rsplit("/", 1)
            folder = "images" if prefix == "/media" else "audio" if prefix == "/audio" else None
            if folder and name == Path(name).name:
                (get_settings().data_dir / folder / name).unlink(missing_ok=True)
        except OSError:
            pass
    return {"words": len(manifest.words), "packs": len(manifest.packs)}
