"""Server-side Pixabay search and image download."""

import asyncio
import hashlib
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import HTTPException

from .config import get_settings
from .media import MAX_BYTES

API_URL = "https://pixabay.com/api/"
CACHE_SECONDS = 24 * 60 * 60
IMAGE_HOSTS = {"pixabay.com", "www.pixabay.com", "cdn.pixabay.com"}


def _api_key() -> str:
    key = get_settings().pixabay_api_key.strip()
    if not key:
        raise HTTPException(
            503, "Pixabay is not configured. Add PIXABAY_API_KEY to .env and restart."
        )
    return key


def _cache_file(params: dict[str, str]) -> Path:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    return get_settings().data_dir / "pixabay-cache" / f"{digest}.json"


def _cached(params: dict[str, str]) -> dict | None:
    try:
        entry = json.loads(_cache_file(params).read_text())
        if time.time() - entry["saved_at"] < CACHE_SECONDS and isinstance(entry["data"], dict):
            return entry["data"]
    except (FileNotFoundError, ValueError, KeyError, TypeError, OSError):
        pass
    return None


def _save_cache(params: dict[str, str], data: dict) -> None:
    path = _cache_file(params)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.{secrets.token_hex(4)}.tmp")
    try:
        temporary.write_text(json.dumps({"saved_at": time.time(), "data": data}))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


async def _fetch_json(params: dict[str, str]) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(API_URL, params={"key": _api_key(), **params})
    except httpx.RequestError as exc:
        raise HTTPException(502, "Could not reach Pixabay. Try again later.") from exc
    if response.status_code == 429:
        raise HTTPException(503, "Pixabay's request limit was reached. Try again later.")
    if response.status_code in (401, 403):
        raise HTTPException(502, "Pixabay rejected the configured API key.")
    if response.status_code != 200:
        raise HTTPException(502, "Pixabay could not complete the search.")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, "Pixabay returned an invalid response.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("hits"), list):
        raise HTTPException(502, "Pixabay returned an invalid response.")
    return data


async def _request(params: dict[str, str]) -> dict:
    _api_key()
    cached = _cached(params)
    if cached is not None:
        return cached
    data = await _fetch_json(params)
    _save_cache(params, data)
    return data


def _pixabay_url(value: str, hosts: set[str]) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname in hosts
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


async def search_images(query: str) -> dict:
    query = query.strip()
    if not query or len(query) > 100:
        raise HTTPException(400, "Enter a search term of 1 to 100 characters.")
    data = await _request({"q": query, "safesearch": "true", "per_page": "12"})
    hits = []
    for hit in data["hits"]:
        if not isinstance(hit, dict):
            continue
        preview = hit.get("previewURL")
        page = hit.get("pageURL")
        if (
            type(hit.get("id")) is int
            and isinstance(preview, str)
            and isinstance(page, str)
            and _pixabay_url(preview, IMAGE_HOSTS)
            and _pixabay_url(page, {"pixabay.com", "www.pixabay.com"})
        ):
            hits.append(
                {
                    "id": hit["id"],
                    "preview_url": preview,
                    "page_url": page,
                    "tags": str(hit.get("tags", "")),
                    "user": str(hit.get("user", "")),
                }
            )
    return {"hits": hits}


async def download_picture(image_id: int) -> bytes:
    data = await _request({"id": str(image_id), "safesearch": "true"})
    hit = next(
        (item for item in data["hits"] if isinstance(item, dict) and item.get("id") == image_id),
        None,
    )
    if hit is None:
        raise HTTPException(404, "Pixabay image not found.")
    url = hit.get("previewURL")
    if not isinstance(url, str) or not _pixabay_url(url, IMAGE_HOSTS):
        raise HTTPException(502, "Pixabay returned an invalid image URL.")
    return await download_image(url)


async def download_image(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for attempt in range(3):
                current_url = url
                for _ in range(4):
                    if not _pixabay_url(current_url, IMAGE_HOSTS):
                        raise HTTPException(502, "Pixabay returned an invalid image URL.")
                    async with client.stream(
                        "GET", current_url, follow_redirects=False
                    ) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise HTTPException(502, "Pixabay returned an invalid redirect.")
                            current_url = urljoin(current_url, location)
                            continue
                        if response.status_code == 429:
                            if attempt == 2:
                                raise HTTPException(
                                    503,
                                    "Pixabay is limiting image downloads. Try again in a minute.",
                                )
                            retry_after = response.headers.get("retry-after", "")
                            delay = int(retry_after) if retry_after.isdecimal() else 2**attempt
                            break
                        if response.status_code != 200:
                            raise HTTPException(
                                502,
                                f"Pixabay could not download the image (HTTP {response.status_code}).",
                            )
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > MAX_BYTES:
                                raise HTTPException(
                                    413, "Pixabay image is too large (8 MB maximum)."
                                )
                        return bytes(data)
                else:
                    raise HTTPException(502, "Pixabay redirected the image too many times.")
                await asyncio.sleep(min(max(delay, 0), 5))
    except httpx.RequestError as exc:
        raise HTTPException(502, "Could not download the Pixabay image.") from exc
    raise HTTPException(502, "Could not download the Pixabay image.")
