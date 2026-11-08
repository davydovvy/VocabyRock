import httpx

from app import wiktapi

from .conftest import run


def test_dictionary_lookup_prefers_us_without_audio_download(client, monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
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
                            {"mp3_url": "https://upload.wikimedia.org/test.mp3", "tags": ["US"]},
                        ],
                    }
                ]
            },
        )

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
        assert "audio" not in lookup
        assert len(requests) == 1
        assert requests[0].url.host == "api.wiktapi.dev"
        assert requests[0].url.params["lang"] == "en"

        saved = await client.post(
            "/api/words",
            json={"english": "tree", "translations": ["дерево"], "ipa": lookup["ipa"]},
        )
        assert saved.status_code == 201
        assert saved.json()["audio"] is None
        assert (
            await client.post(
                "/api/words",
                json={
                    "english": "forest",
                    "translations": ["лес"],
                    "audio_url": "https://upload.wikimedia.org/test.mp3",
                },
            )
        ).status_code == 422
        assert (
            await client.post(f"/api/words/{saved.json()['id']}/audio/retry")
        ).status_code == 405

    run(scenario())


def test_us_accent_tags_include_california():
    assert wiktapi._priority(["California"]) < wiktapi._priority(["London"])


def test_lookup_keeps_pronunciations_with_their_meanings(client, monkeypatch):
    def respond(request):
        return httpx.Response(
            200,
            json={
                "word": "live",
                "entries": [
                    {
                        "pos": "verb",
                        "translations": [{"lang_code": "ru", "word": "жить", "sense": "to reside"}],
                        "sounds": [{"ipa": "/lɪv/", "tags": ["US"]}],
                    },
                    {
                        "pos": "adjective",
                        "translations": [
                            {"lang_code": "ru", "word": "живой", "sense": "broadcast in real time"}
                        ],
                        "sounds": [{"ipa": "/laɪv/", "tags": ["US"]}],
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
        assert "audio" not in result

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


def test_dictionary_missing_entry_keeps_fields_blank(client, monkeypatch):
    async def missing(word):
        return {"translations": [], "ipa": "", "part_of_speech": "", "us_spelling": ""}

    monkeypatch.setattr(wiktapi, "lookup", missing)

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        assert (await client.get("/api/dictionary?word=unknown")).json() == await missing("unknown")
        saved = await client.post(
            "/api/words",
            json={"english": "unknown", "translations": ["вручную"]},
        )
        assert saved.status_code == 201
        assert saved.json()["audio"] is None

    run(scenario())
