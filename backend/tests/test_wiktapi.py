import httpx
from datetime import timedelta

from app import audio_jobs, wiktapi
from app.models import Word, now

from .conftest import run


def test_dictionary_lookup_prefers_us_and_saves_offline_audio(
    client, database, monkeypatch, tmp_path
):
    monkeypatch.setattr(audio_jobs, "_cooldown_until", None)
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
            assert db.get(Word, second["id"]).audio_next_attempt_at >= queued.audio_next_attempt_at
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


def test_failed_audio_can_be_requeued(client, database, monkeypatch):
    monkeypatch.setattr(audio_jobs, "_cooldown_until", None)

    async def limited(url):
        raise wiktapi.AudioRateLimited(10)

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
