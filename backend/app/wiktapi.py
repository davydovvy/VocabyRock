"""Look up English words and store selected Wikimedia pronunciations locally."""

import secrets
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException

from .config import get_settings

API_URL = "https://api.wiktapi.dev/v1/en/word"
SEARCH_URL = "https://api.wiktapi.dev/v1/en/search"
MAX_AUDIO_BYTES = 8 * 1024 * 1024
US_TAGS = {"US", "USA", "United-States", "General-American", "American", "California"}
OTHER_TAGS = {"UK", "British", "Received-Pronunciation", "Australia", "New-Zealand", "London"}
WIKIMEDIA_USER_AGENT = "VacabyRock/1.0 (personal vocabulary learning app; pronunciation download)"


class AudioRateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Wikimedia is limiting downloads")


def _retry_after(value: str) -> int:
    if value.isdigit():
        return max(1, int(value))
    try:
        return max(
            1, int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        )
    except (TypeError, ValueError, OverflowError):
        return 30


def validate_audio_url(url: str) -> None:
    if not _audio_url(url):
        raise HTTPException(400, "Choose a Wikimedia pronunciation from the dictionary.")


def _priority(tags: list[str]) -> int:
    if US_TAGS.intersection(tags):
        return 0
    if OTHER_TAGS.intersection(tags):
        return 2
    return 1


def _audio_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "upload.wikimedia.org"
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and parsed.path.startswith("/wikipedia/commons/")
            and parsed.path.lower().endswith((".mp3", ".ogg"))
        )
    except ValueError:
        return False


def _entry_payload(response: httpx.Response) -> tuple[dict, list]:
    try:
        payload = response.json()
        entries = payload["entries"]
        if not isinstance(payload, dict) or not isinstance(entries, list):
            raise ValueError
        return payload, entries
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(502, "WiktAPI returned an invalid entry.") from exc


def _has_russian_translations(entries: list) -> bool:
    return any(
        isinstance(translation, dict)
        and translation.get("lang_code", translation.get("code")) == "ru"
        and isinstance(translation.get("word"), str)
        and translation["word"].strip()
        for entry in entries
        if isinstance(entry, dict)
        for translation in (entry.get("translations") or [])
    )


async def lookup(word: str) -> dict:
    word = " ".join(word.split())
    if not word or len(word) > 160:
        raise HTTPException(400, "Enter an English word of 1 to 160 characters.")
    resolved_word = word
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(f"{API_URL}/{quote(word, safe='')}", params={"lang": "en"})
            lowercase = word.lower()
            if lowercase != word and response.status_code in (200, 404):
                original_entries = (
                    _entry_payload(response)[1] if response.status_code == 200 else []
                )
                if not _has_russian_translations(original_entries):
                    lowercase_response = await client.get(
                        f"{API_URL}/{quote(lowercase, safe='')}", params={"lang": "en"}
                    )
                    if lowercase_response.status_code == 200:
                        _, lowercase_entries = _entry_payload(lowercase_response)
                        if lowercase_entries:
                            response = lowercase_response
                            resolved_word = lowercase
            if response.status_code == 404:
                search = await client.get(SEARCH_URL, params={"q": word, "lang": "en"})
                if search.status_code != 200:
                    raise HTTPException(502, "WiktAPI could not complete the lookup.")
                try:
                    results = search.json()["results"]
                    if not isinstance(results, list):
                        raise ValueError
                except (ValueError, KeyError, TypeError) as exc:
                    raise HTTPException(502, "WiktAPI returned an invalid search result.") from exc
                match = next(
                    (
                        result["word"]
                        for result in results
                        if isinstance(result, dict)
                        and isinstance(result.get("word"), str)
                        and result.get("lang_code") == "en"
                        and result["word"].casefold() == word.casefold()
                    ),
                    None,
                )
                if match:
                    resolved_word = match
                    response = await client.get(
                        f"{API_URL}/{quote(match, safe='')}", params={"lang": "en"}
                    )
    except httpx.RequestError as exc:
        raise HTTPException(
            502, "Could not reach WiktAPI. You can fill the word manually."
        ) from exc
    if response.status_code == 404:
        return {
            "word": "",
            "translations": [],
            "ipa": "",
            "audio": [],
            "part_of_speech": "",
            "us_spelling": "",
        }
    if response.status_code != 200:
        raise HTTPException(502, "WiktAPI could not complete the lookup.")
    payload, entries = _entry_payload(response)
    try:
        canonical_word = payload.get("word")
        if not isinstance(canonical_word, str) or canonical_word.casefold() != word.casefold():
            canonical_word = next(
                (
                    entry["word"]
                    for entry in entries
                    if isinstance(entry, dict)
                    and isinstance(entry.get("word"), str)
                    and entry["word"].casefold() == word.casefold()
                ),
                resolved_word,
            )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(502, "WiktAPI returned an invalid entry.") from exc

    translations = []
    sounds = []
    part_of_speech = ""
    us_spelling = ""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not part_of_speech and isinstance(entry.get("pos"), str):
            part_of_speech = entry["pos"]
        for form in entry.get("forms", []):
            if (
                isinstance(form, dict)
                and isinstance(form.get("form"), str)
                and "alternative" in (form.get("tags") or [])
                and US_TAGS.intersection(form.get("tags") or [])
                and form["form"].casefold() != word.casefold()
            ):
                us_spelling = form["form"]
                break
        for item in entry.get("translations", []):
            if not isinstance(item, dict) or item.get("lang_code", item.get("code")) != "ru":
                continue
            value = item.get("word")
            if isinstance(value, str) and value.strip():
                suggestion = {"word": value.strip(), "sense": item.get("sense") or ""}
                if suggestion not in translations:
                    translations.append(suggestion)
        for sound in entry.get("sounds", []):
            if isinstance(sound, dict):
                sounds.append(sound)

    ipa = next(
        (
            sound["ipa"]
            for sound in sorted(sounds, key=lambda s: _priority(s.get("tags") or []))
            if isinstance(sound.get("ipa"), str) and sound["ipa"]
        ),
        "",
    )
    audio = []
    seen_urls = set()
    for sound in sorted(sounds, key=lambda s: _priority(s.get("tags") or [])):
        url = sound.get("mp3_url") or sound.get("ogg_url")
        if not isinstance(url, str) or not _audio_url(url) or url in seen_urls:
            continue
        seen_urls.add(url)
        audio.append(
            {
                "url": url,
                "label": sound.get("audio") or "Pronunciation",
                "tags": sound.get("tags") or [],
            }
        )
    return {
        "word": canonical_word,
        "translations": translations,
        "ipa": ipa,
        "audio": audio,
        "part_of_speech": part_of_speech,
        "us_spelling": us_spelling,
    }


async def save_audio(url: str) -> str:
    validate_audio_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=False,
            headers={"User-Agent": WIKIMEDIA_USER_AGENT},
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code == 429:
                    raise AudioRateLimited(_retry_after(response.headers.get("retry-after", "")))
                if response.status_code == 403:
                    raise HTTPException(502, "Wikimedia rejected the pronunciation download.")
                if response.status_code != 200:
                    raise HTTPException(502, "Could not download the pronunciation.")
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                if content_type not in {"audio/mpeg", "audio/mp3", "audio/ogg", "application/ogg"}:
                    raise HTTPException(502, "The pronunciation has an unsupported audio format.")
                suffix = ".mp3" if urlsplit(url).path.lower().endswith(".mp3") else ".ogg"
                folder = get_settings().data_dir / "audio"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{secrets.token_hex(16)}{suffix}"
                size = 0
                try:
                    with path.open("wb") as file:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > MAX_AUDIO_BYTES:
                                raise HTTPException(
                                    413, "Pronunciation is too large (8 MB maximum)."
                                )
                            file.write(chunk)
                    if not size:
                        raise HTTPException(502, "The pronunciation was empty.")
                except BaseException:
                    path.unlink(missing_ok=True)
                    raise
                return f"/audio/{path.name}"
    except httpx.RequestError as exc:
        raise HTTPException(502, "Could not download the pronunciation.") from exc


def remove_audio(url: str | None) -> None:
    if url and url.startswith("/audio/"):
        (get_settings().data_dir / "audio" / Path(url).name).unlink(missing_ok=True)
