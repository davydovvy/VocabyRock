"""Import selected Kokoro WAV takes into an existing word pack."""

import io
import re
import secrets
import wave
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .config import get_settings
from .media import remove_audio
from .models import Pack

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_BATCH_BYTES = 64 * 1024 * 1024
MAX_FILES = 100
NAME_PATTERN = re.compile(r"^([0-9a-fA-F-]{36})--[^/\\]+\.wav$", re.IGNORECASE)


def _word_guid(filename: str) -> str:
    match = NAME_PATTERN.fullmatch(filename)
    if not match:
        raise HTTPException(400, f"{filename}: WAV filename must start with a word GUID and --.")
    try:
        guid = str(UUID(match.group(1)))
    except ValueError as exc:
        raise HTTPException(400, f"{filename}: invalid word GUID.") from exc
    if guid != match.group(1).lower():
        raise HTTPException(400, f"{filename}: use the full canonical word GUID.")
    return guid


def _check_wav(content: bytes, filename: str) -> None:
    try:
        with wave.open(io.BytesIO(content), "rb") as recording:
            frames = recording.getnframes()
            valid = (
                recording.getnchannels() == 1
                and recording.getframerate() == 24000
                and recording.getsampwidth() == 2
                and recording.getcomptype() == "NONE"
                and frames > 0
                and len(recording.readframes(frames)) == frames * 2
            )
    except (EOFError, OSError, wave.Error) as exc:
        raise HTTPException(400, f"{filename}: invalid WAV file.") from exc
    if not valid:
        raise HTTPException(400, f"{filename}: expected mono 24 kHz 16-bit PCM WAV.")


async def import_audio(pack: Pack, files: list[UploadFile], db: Session) -> dict:
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f"Choose 1 to {MAX_FILES} WAV files at a time.")
    words = {item.word.guid: item.word for item in pack.words}
    selected: dict[str, bytes] = {}
    duplicates = 0
    total_bytes = 0
    for file in files:
        name = file.filename or ""
        guid = _word_guid(name)
        if guid not in words:
            raise HTTPException(400, f"{name}: word is not in this pack.")
        content = await file.read(MAX_AUDIO_BYTES + 1)
        if len(content) > MAX_AUDIO_BYTES:
            raise HTTPException(413, f"{name}: WAV file exceeds 8 MB.")
        total_bytes += len(content)
        if total_bytes > MAX_BATCH_BYTES:
            raise HTTPException(413, "Audio upload exceeds 64 MB; upload in smaller batches.")
        _check_wav(content, name)
        if guid in selected:
            duplicates += 1
            continue
        selected[guid] = content

    directory = get_settings().data_dir / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    replaced: list[str | None] = []
    try:
        for guid, content in selected.items():
            path = directory / f"{secrets.token_hex(16)}.wav"
            path.write_bytes(content)
            created.append(path)
            word = words[guid]
            replaced.append(word.audio)
            word.audio = f"/audio/{path.name}"
        db.commit()
    except Exception:
        db.rollback()
        for path in created:
            path.unlink(missing_ok=True)
        raise
    for old in replaced:
        remove_audio(old)
    return {"imported": len(selected), "duplicates": duplicates}
