import io
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from .config import get_settings

ALLOWED = {"JPEG", "PNG", "WEBP"}
MAX_BYTES = 8 * 1024 * 1024


async def save_picture(upload: UploadFile) -> str:
    data = await upload.read(MAX_BYTES + 1)
    return save_picture_data(data)


def save_picture_data(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Picture is too large (8 MB maximum)")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data))
        if image.format not in ALLOWED or image.width * image.height > 25_000_000:
            raise ValueError("Unsupported picture")
        image.thumbnail((640, 640), Image.Resampling.LANCZOS)
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(400, "Please use a JPEG, PNG, or WebP picture") from exc
    folder = get_settings().data_dir / "images"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.webp"
    image.save(folder / name, "WEBP", quality=85)
    return f"/media/{name}"


def remove_picture(path: str | None):
    if path and path.startswith("/media/"):
        (get_settings().data_dir / "images" / Path(path).name).unlink(missing_ok=True)
