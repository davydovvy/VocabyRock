import io

import httpx
from PIL import Image

from app import pixabay
from app.config import get_settings

from .conftest import run


def test_pixabay_image_download_retries_rate_limit(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, content=b"image bytes")

    transport = httpx.MockTransport(respond)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        pixabay.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    assert run(pixabay.download_image("https://pixabay.com/get/picture_640.jpg")) == b"image bytes"
    assert len(requests) == 2


def test_pixabay_requires_parent_and_api_key(client):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(profile for profile in profiles if profile["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        assert (await client.get("/api/pixabay/search?q=cat")).status_code == 403
        assert (
            await client.get(
                "/api/pixabay/preview",
                params={"url": "https://cdn.pixabay.com/photo/cat_150.jpg"},
            )
        ).status_code == 403
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        missing = await client.get("/api/pixabay/search?q=cat")
        assert missing.status_code == 503
        assert "PIXABAY_API_KEY" in missing.json()["detail"]
        assert (await client.get("/api/pixabay/search?q=%20")).status_code == 400

    run(scenario())


def test_pixabay_search_cache_and_local_picture(client, monkeypatch, tmp_path):
    monkeypatch.setenv("PIXABAY_API_KEY", "test-key")
    get_settings.cache_clear()
    requests = []

    async def fake_fetch(params):
        requests.append(params)
        if "q" in params:
            return {
                "hits": [
                    {
                        "id": 42,
                        "previewURL": "https://cdn.pixabay.com/photo/cat_150.jpg",
                        "webformatURL": "https://pixabay.com/get/cat_640.jpg",
                        "pageURL": "https://pixabay.com/photos/cat-42/",
                        "tags": "cat, pet",
                        "user": "Contributor",
                    },
                    {
                        "id": 43,
                        "previewURL": "https://other.example/cat.jpg",
                        "webformatURL": "https://other.example/cat_640.jpg",
                        "pageURL": "https://pixabay.com/photos/other-43/",
                    },
                ]
            }
        return {
            "hits": [
                {
                    "id": int(params["id"]),
                    "previewURL": "https://cdn.pixabay.com/photo/cat_150.jpg",
                    "webformatURL": "https://pixabay.com/get/cat_640.jpg",
                }
            ]
        }

    image = Image.new("RGB", (800, 500), "orange")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    downloads = []

    async def fake_download(url):
        assert url == "https://pixabay.com/get/cat_640.jpg"
        downloads.append(url)
        return buffer.getvalue()

    monkeypatch.setattr(pixabay, "_fetch_json", fake_fetch)
    monkeypatch.setattr(pixabay, "download_image", fake_download)

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        first = (await client.get("/api/pixabay/search?q=cat")).json()
        second = (await client.get("/api/pixabay/search?q=cat")).json()
        assert first == second
        assert len(first["hits"]) == 1
        assert first["hits"][0]["id"] == 42
        preview_url = first["hits"][0]["preview_url"]
        assert preview_url.startswith("/api/pixabay/preview?url=")
        assert "pixabay.com%2Fget%2Fcat_640.jpg" in preview_url
        preview = await client.get(preview_url)
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/webp"
        assert Image.open(io.BytesIO(preview.content)).format == "WEBP"
        assert (await client.get(preview_url)).content == preview.content
        assert len(downloads) == 1
        assert len(requests) == 1
        assert list((tmp_path / "pixabay-cache").glob("*.json"))
        assert len(list((tmp_path / "pixabay-cache" / "previews").glob("*.webp"))) == 1
        assert (
            await client.get("/api/pixabay/preview", params={"url": "https://evil.example/a.jpg"})
        ).status_code == 400

        word = (
            await client.post("/api/words", json={"english": "tree", "translations": ["дерево"]})
        ).json()
        saved = await client.post(f"/api/words/{word['id']}/pixabay", json={"image_id": 42})
        assert saved.status_code == 200
        picture = saved.json()["picture"]
        assert picture.startswith("/media/")
        served = await client.get(picture)
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/webp"
        assert (await client.get(f"/api/words/{word['id']}")).json()["picture"] == picture
        assert len(downloads) == 1
        assert requests == [{"q": "cat", "safesearch": "true", "per_page": "12"}]

    run(scenario())


def test_pixabay_rejects_untrusted_download_url(client, monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "test-key")
    get_settings.cache_clear()

    async def fake_fetch(_params):
        return {"hits": [{"id": 99, "webformatURL": "https://evil.example/image.jpg"}]}

    monkeypatch.setattr(pixabay, "_fetch_json", fake_fetch)

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        word = (
            await client.post("/api/words", json={"english": "tree", "translations": ["дерево"]})
        ).json()
        result = await client.post(f"/api/words/{word['id']}/pixabay", json={"image_id": 99})
        assert result.status_code == 502
        assert (await client.get(f"/api/words/{word['id']}")).json()["picture"] is None

    run(scenario())
