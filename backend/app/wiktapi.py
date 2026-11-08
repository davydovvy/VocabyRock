"""Look up English words, translations, and IPA through WiktAPI."""

from urllib.parse import quote

import httpx
from fastapi import HTTPException

API_URL = "https://api.wiktapi.dev/v1/en/word"
SEARCH_URL = "https://api.wiktapi.dev/v1/en/search"
US_TAGS = {"US", "USA", "United-States", "General-American", "American", "California"}
OTHER_TAGS = {"UK", "British", "Received-Pronunciation", "Australia", "New-Zealand", "London"}


def _priority(tags: list[str]) -> int:
    if US_TAGS.intersection(tags):
        return 0
    if OTHER_TAGS.intersection(tags):
        return 2
    return 1


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
    for entry_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if not part_of_speech and isinstance(entry.get("pos"), str):
            part_of_speech = entry["pos"]
        entry_sounds = [sound for sound in entry.get("sounds", []) if isinstance(sound, dict)]
        ranked_sounds = sorted(entry_sounds, key=lambda sound: _priority(sound.get("tags") or []))
        entry_ipa = next(
            (
                sound["ipa"]
                for sound in ranked_sounds
                if isinstance(sound.get("ipa"), str) and sound["ipa"]
            ),
            "",
        )
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
                suggestion = {
                    "word": value.strip(),
                    "sense": item.get("sense") or "",
                    "entry_index": entry_index,
                    "part_of_speech": entry.get("pos") or "",
                    "ipa": entry_ipa,
                }
                if suggestion not in translations:
                    translations.append(suggestion)
        sounds.extend(entry_sounds)
    ipa = next(
        (
            sound["ipa"]
            for sound in sorted(sounds, key=lambda s: _priority(s.get("tags") or []))
            if isinstance(sound.get("ipa"), str) and sound["ipa"]
        ),
        "",
    )
    return {
        "word": canonical_word,
        "translations": translations,
        "ipa": ipa,
        "part_of_speech": part_of_speech,
        "us_spelling": us_spelling,
    }
