import asyncio

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from datetime import timedelta

from app import audio_jobs, wiktapi
from app.config import get_settings
from app.main import app
from app.models import Word, now

from .conftest import run


def test_disabled_audio_downloads_leave_queue_untouched(database, monkeypatch):
    url = "https://upload.wikimedia.org/wikipedia/commons/a/ab/tree.mp3"
    with database() as db:
        word = Word(english="tree", translations=["дерево"])
        audio_jobs.queue_audio(word, url)
        db.add(word)
        db.commit()
        word_id = word.id

    monkeypatch.setenv("AUDIO_DOWNLOADS_ENABLED", "false")
    get_settings.cache_clear()

    async def fail_if_downloaded(_url):
        raise AssertionError("Audio download should be disabled")

    monkeypatch.setattr(wiktapi, "save_audio", fail_if_downloaded)
    assert not run(audio_jobs.process_due(database))

    async def fail_if_started():
        raise AssertionError("Audio worker should be disabled")

    monkeypatch.setattr(audio_jobs, "run_worker", fail_if_started)

    async def check_lifespan():
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)

    run(check_lifespan())
    with database() as db:
        queued = db.get(Word, word_id)
        assert queued.audio_status == "pending"
        assert queued.audio_attempts == 0
        assert queued.audio_next_attempt_at is not None


def test_dictionary_lookup_prefers_us_and_saves_offline_audio(
    client, database, monkeypatch, tmp_path
):
    monkeypatch.setattr(audio_jobs, "_cooldown_until", None)
    monkeypatch.setattr(audio_jobs, "_rate_limit_streak", 0)
    audio_url = "https://upload.wikimedia.org/wikipedia/commons/a/ab/tree.mp3"
    requests = []
    audio_requests = []

    def respond(request):
        requests.append(request)
        if request.url.host == "api.wiktapi.dev":
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {
                            "pos": "noun",
                            "forms": [{"form": "treez", "tags": ["alternative", "US"]}],
                            "translations": [
                                {"lang_code": "ru", "word": "де́рево", "sense": "large woody plant"},
                                {"code": "ru", "word": "дре́во", "sense": "poetic"},
                                {"code": "fr", "word": "arbre"},
                            ],
                            "sounds": [
                                {"ipa": "/UK/", "tags": ["UK"]},
                                {"ipa": "/US/", "tags": ["General-American"]},
                                {"mp3_url": audio_url, "audio": "tree.mp3", "tags": ["US"]},
                            ],
                        }
                    ]
                },
            )
        if str(request.url) == audio_url:
            audio_requests.append(request)
            if request.headers.get("user-agent") != wiktapi.WIKIMEDIA_USER_AGENT:
                return httpx.Response(403, text="Please set a user-agent")
            if len(audio_requests) == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, content=b"recording", headers={"content-type": "audio/mpeg"})
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        wiktapi.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )

    async def scenario():
        assert (await client.get("/api/dictionary?word=tree")).status_code == 401
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        lookup = (await client.get("/api/dictionary?word=tree")).json()
        assert lookup["word"] == "tree"
        assert lookup["ipa"] == "/US/"
        assert lookup["part_of_speech"] == "noun"
        assert lookup["us_spelling"] == "treez"
        assert [item["word"] for item in lookup["translations"]] == ["де́рево", "дре́во"]
        assert lookup["audio"][0]["url"] == audio_url
        assert requests[0].url.params["lang"] == "en"

        saved = await client.post(
            "/api/words",
            json={
                "english": "tree",
                "translations": ["де́рево"],
                "ipa": lookup["ipa"],
                "audio_url": audio_url,
            },
        )
        assert saved.status_code == 201
        word = saved.json()
        assert word["audio"] is None
        assert word["audio_status"] == "pending"
        assert not audio_requests
        second = (
            await client.post(
                "/api/words",
                json={"english": "forest", "translations": ["лес"], "audio_url": audio_url},
            )
        ).json()
        assert await audio_jobs.process_due(database)
        assert len(audio_requests) == 1
        with database() as db:
            queued = db.get(Word, word["id"])
            assert queued.audio_status == "retrying"
            assert queued.audio_next_attempt_at > now()
            assert db.get(Word, second["id"]).audio_next_attempt_at <= queued.audio_next_attempt_at
            queued.audio_next_attempt_at = now() - timedelta(seconds=1)
            db.commit()
        assert not await audio_jobs.process_due(database)
        monkeypatch.setattr(audio_jobs, "_cooldown_until", None)
        assert await audio_jobs.process_due(database)
        assert len(audio_requests) == 2
        word = (await client.get(f"/api/words/{word['id']}")).json()
        assert word["audio_status"] == "ready"
        assert word["audio"].startswith("/audio/")
        assert (tmp_path / "audio" / word["audio"].split("/")[-1]).read_bytes() == b"recording"
        response = await client.get(word["audio"])
        assert response.content == b"recording"
        assert response.headers["content-type"].startswith("audio/mpeg")
        assert (
            await client.post(
                "/api/words",
                json={
                    "english": "bad",
                    "translations": ["плохой"],
                    "audio_url": "https://example.com/bad.mp3",
                },
            )
        ).status_code == 400
        await client.delete(f"/api/words/{word['id']}")
        assert not (tmp_path / "audio" / word["audio"].split("/")[-1]).exists()

    run(scenario())


def test_us_accent_tags_include_california():
    assert wiktapi._priority(["California"]) < wiktapi._priority(["London"])


def test_rate_limit_never_permanently_fails_audio(database, monkeypatch):
    monkeypatch.setattr(audio_jobs, "_cooldown_until", None)
    monkeypatch.setattr(audio_jobs, "_rate_limit_streak", 0)
    with database() as db:
        word = Word(english="test audio", translations=["тест"])
        audio_jobs.queue_audio(
            word, "https://upload.wikimedia.org/wikipedia/commons/a/ab/test-audio.mp3"
        )
        db.add(word)
        db.commit()
        word_id = word.id

    async def limited(_url):
        raise wiktapi.AudioRateLimited(10)

    monkeypatch.setattr(wiktapi, "save_audio", limited)

    async def scenario():
        for _ in range(audio_jobs.MAX_ATTEMPTS + 1):
            monkeypatch.setattr(audio_jobs, "_cooldown_until", None)
            with database() as db:
                saved = db.get(Word, word_id)
                saved.audio_next_attempt_at = now() - timedelta(seconds=1)
                db.commit()
            assert await audio_jobs.process_due(database)
        with database() as db:
            saved = db.get(Word, word_id)
            assert saved.audio_status == "retrying"
            assert saved.audio_attempts == 0
            assert saved.audio_error == audio_jobs.RATE_LIMIT_ERROR

    run(scenario())


def test_old_rate_limit_failures_are_restored(database, monkeypatch):
    monkeypatch.setattr(audio_jobs, "_cooldown_until", None)
    with database() as db:
        word = Word(
            english="old failed audio",
            translations=["старый"],
            audio_source_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/old.mp3",
            audio_status="failed",
            audio_attempts=8,
            audio_error=audio_jobs.EXHAUSTED_RATE_LIMIT_ERROR,
        )
        db.add(word)
        db.commit()
        word_id = word.id
    assert audio_jobs.recover_rate_limited_failures(database) == 1
    assert audio_jobs.recover_rate_limited_failures(database) == 0
    with database() as db:
        saved = db.get(Word, word_id)
        assert saved.audio_status == "retrying"
        assert saved.audio_attempts == 0
        assert saved.audio_next_attempt_at is not None


def test_worker_restores_rate_limit_cooldown_after_restart(database, monkeypatch):
    monkeypatch.setattr(audio_jobs, "_cooldown_until", None)
    due = now() + timedelta(minutes=5)
    with database() as db:
        db.add_all(
            [
                Word(
                    english="limited",
                    translations=["ограниченный"],
                    audio_status="retrying",
                    audio_source_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/limited.mp3",
                    audio_error=audio_jobs.RATE_LIMIT_ERROR,
                    audio_next_attempt_at=due,
                ),
                Word(
                    english="waiting",
                    translations=["ожидающий"],
                    audio_status="pending",
                    audio_source_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/waiting.mp3",
                    audio_next_attempt_at=due,
                ),
            ]
        )
        db.commit()
    assert audio_jobs.recover_rate_limited_failures(database) == 0
    assert audio_jobs._cooldown_until == due
    with database() as db:
        waiting = db.scalar(select(Word).where(Word.english == "waiting"))
        assert waiting.audio_error == audio_jobs.RATE_LIMIT_ERROR


def test_lookup_keeps_pronunciations_with_their_meanings(client, monkeypatch):
    verb_audio = "https://upload.wikimedia.org/wikipedia/commons/a/ab/live-verb.mp3"
    adjective_audio = "https://upload.wikimedia.org/wikipedia/commons/a/ab/live-adjective.mp3"

    def respond(request):
        return httpx.Response(
            200,
            json={
                "word": "live",
                "entries": [
                    {
                        "pos": "verb",
                        "translations": [{"lang_code": "ru", "word": "жить", "sense": "to reside"}],
                        "sounds": [
                            {"ipa": "/lɪv/", "tags": ["US"]},
                            {"mp3_url": verb_audio, "tags": ["US"]},
                        ],
                    },
                    {
                        "pos": "adjective",
                        "translations": [
                            {"lang_code": "ru", "word": "живой", "sense": "broadcast in real time"}
                        ],
                        "sounds": [
                            {"ipa": "/laɪv/", "tags": ["US"]},
                            {"mp3_url": adjective_audio, "tags": ["US"]},
                        ],
                    },
                ],
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        wiktapi.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        result = (await client.get("/api/dictionary?word=live")).json()
        assert [
            (item["word"], item["ipa"], item["part_of_speech"], item["entry_index"])
            for item in result["translations"]
        ] == [
            ("жить", "/lɪv/", "verb", 0),
            ("живой", "/laɪv/", "adjective", 1),
        ]
        assert [(item["url"], item["entry_index"]) for item in result["audio"]] == [
            (verb_audio, 0),
            (adjective_audio, 1),
        ]

    run(scenario())


def test_dictionary_lookup_resolves_case_insensitive_headwords(client, monkeypatch):
    requests = []

    def respond(request):
        requests.append(str(request.url))
        word = request.url.path.rsplit("/", 1)[-1]
        if request.url.path.endswith("/search"):
            if request.url.params["q"].casefold() == "january":
                results = [
                    {"word": "Januaryish", "lang_code": "en"},
                    {"word": "January", "lang_code": "en"},
                    {"word": "january", "lang_code": "fr"},
                ]
            else:
                results = [{"word": request.url.params["q"].capitalize(), "lang_code": "en"}]
                if request.url.params["q"].casefold() == "mountain":
                    results = [{"word": "mountain", "lang_code": "en"}]
            return httpx.Response(
                200,
                json={"results": results},
            )
        if word == "January":
            return httpx.Response(200, json={"word": "January", "entries": [{"pos": "name"}]})
        if word == "Mountain":
            return httpx.Response(200, json={"word": "Mountain", "entries": [{"pos": "name"}]})
        if word == "mountain":
            return httpx.Response(
                200,
                json={
                    "word": "mountain",
                    "entries": [
                        {"pos": "noun", "translations": [{"lang_code": "ru", "word": "гора"}]}
                    ],
                },
            )
        if word == "Monk":
            return httpx.Response(200, json={"word": "Monk", "entries": [{"pos": "name"}]})
        if word == "monk":
            return httpx.Response(
                200,
                json={
                    "word": "monk",
                    "entries": [
                        {"pos": "noun", "translations": [{"lang_code": "ru", "word": "монах"}]}
                    ],
                },
            )
        if word == "Germany":
            return httpx.Response(200, json={"word": "Germany", "entries": [{"pos": "name"}]})
        if word == "Turkey":
            return httpx.Response(
                200,
                json={
                    "word": "Turkey",
                    "entries": [
                        {"pos": "name", "translations": [{"lang_code": "ru", "word": "Турция"}]}
                    ],
                },
            )
        if word == "turkey":
            return httpx.Response(
                200,
                json={
                    "word": "turkey",
                    "entries": [
                        {"pos": "noun", "translations": [{"lang_code": "ru", "word": "индейка"}]}
                    ],
                },
            )
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        wiktapi.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        january = (await client.get("/api/dictionary?word=jAnUaRy")).json()
        assert january["word"] == "January"
        assert january["part_of_speech"] == "name"
        assert requests[-1].endswith("/word/January?lang=en")

        mountain = (await client.get("/api/dictionary?word=Mountain")).json()
        assert mountain["word"] == "mountain"
        assert mountain["part_of_speech"] == "noun"
        assert mountain["translations"][0]["word"] == "гора"
        assert requests[-1].endswith("/word/mountain?lang=en")

        monk = (await client.get("/api/dictionary?word=Monk")).json()
        assert monk["word"] == "monk"
        assert monk["translations"][0]["word"] == "монах"
        assert requests[-1].endswith("/word/monk?lang=en")

        germany = (await client.get("/api/dictionary?word=GERMANY")).json()
        assert germany["word"] == "Germany"

        turkey = (await client.get("/api/dictionary?word=Turkey")).json()
        assert turkey["word"] == "Turkey"
        assert turkey["translations"][0]["word"] == "Турция"

    run(scenario())


def test_failed_audio_can_be_requeued(client, database, monkeypatch):
    monkeypatch.setattr(audio_jobs, "_cooldown_until", None)

    async def limited(url):
        raise HTTPException(502, "Could not download the pronunciation.")

    monkeypatch.setattr(wiktapi, "save_audio", limited)

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        saved = (
            await client.post(
                "/api/words",
                json={
                    "english": "mountain",
                    "translations": ["гора"],
                    "audio_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/mountain.mp3",
                },
            )
        ).json()
        with database() as db:
            word = db.get(Word, saved["id"])
            word.audio_attempts = audio_jobs.MAX_ATTEMPTS - 1
            db.commit()
        assert await audio_jobs.process_due(database)
        failed = (await client.get(f"/api/words/{saved['id']}")).json()
        assert failed["audio_status"] == "failed"
        assert failed["audio"] is None
        retried = await client.post(f"/api/words/{saved['id']}/audio/retry")
        assert retried.status_code == 200
        assert retried.json()["audio_status"] == "pending"
        assert retried.json()["audio_attempts"] == 0

    run(scenario())


def test_dictionary_missing_entry_keeps_fields_blank(client, monkeypatch):
    async def missing(word):
        return {"translations": [], "ipa": "", "audio": [], "part_of_speech": "", "us_spelling": ""}

    monkeypatch.setattr(wiktapi, "lookup", missing)

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        assert (await client.get("/api/dictionary?word=unknown")).json() == await missing("unknown")
        saved = await client.post(
            "/api/words",
            json={
                "english": "unknown",
                "translations": ["вручную"],
            },
        )
        assert saved.status_code == 201
        assert saved.json()["audio"] is None

    run(scenario())
