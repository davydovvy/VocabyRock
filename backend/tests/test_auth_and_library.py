import io

from PIL import Image

from app.auth import clear_failed_logins, login_allowed, record_failed_login

from .conftest import run


def test_parent_login_and_admin_authorization(client):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(p for p in profiles if p["role"] == "child")
        assert (
            await client.post("/api/auth/child", json={"user_id": child["id"]})
        ).status_code == 200
        assert (
            await client.post("/api/words", json={"english": "tree", "translations": ["дерево"]})
        ).status_code == 403
        assert (await client.post("/api/auth/parent", json={"password": "bad"})).status_code == 401
        assert (
            await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        ).status_code == 200
        assert (await client.get("/api/settings")).status_code == 200
        assert (
            await client.post("/api/words", json={"english": "   ", "translations": ["слово"]})
        ).status_code == 422
        assert (await client.post("/api/packs", json={"name": "   "})).status_code == 422
        assert (await client.post("/api/auth/logout")).status_code == 200
        assert (await client.get("/api/settings")).status_code == 401

    run(scenario())


def test_word_crud_and_shared_pack_membership(client):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        word = (
            await client.post(
                "/api/words", json={"english": "bank", "translations": ["банк"], "ipa": "/bæŋk/"}
            )
        ).json()
        assert word["english"] == "bank"
        second = (
            await client.post("/api/words", json={"english": "shore", "translations": ["берег"]})
        ).json()
        assert second["id"] != word["id"]
        pack = (
            await client.post("/api/packs", json={"name": "Places", "description": "Go places"})
        ).json()
        other = (
            await client.post("/api/packs", json={"name": "Money", "description": "Money words"})
        ).json()
        assert (
            await client.put(
                f"/api/packs/{pack['id']}/words", json={"word_ids": [word["id"], second["id"]]}
            )
        ).status_code == 200
        reordered = (
            await client.put(
                f"/api/packs/{pack['id']}/words", json={"word_ids": [second["id"], word["id"]]}
            )
        ).json()
        assert reordered["word_ids"] == [second["id"], word["id"]]
        await client.put(f"/api/packs/{other['id']}/words", json={"word_ids": [word["id"]]})
        edited = (
            await client.put(
                f"/api/words/{word['id']}",
                json={"english": "bank", "translations": ["банк", "финансовое учреждение"]},
            )
        ).json()
        assert len(edited["translations"]) == 2
        assert (await client.delete(f"/api/packs/{pack['id']}")).status_code == 200
        assert (await client.get(f"/api/words/{word['id']}")).status_code == 200
        assert (await client.get(f"/api/packs/{other['id']}")).json()["word_ids"] == [word["id"]]
        assert (await client.delete(f"/api/words/{word['id']}")).status_code == 200
        assert (await client.get(f"/api/packs/{other['id']}")).json()["word_ids"] == []

    run(scenario())


def test_pack_word_creation_and_duplicate_rejection(client):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        pack = (await client.post("/api/packs", json={"name": "Mountains"})).json()
        created = await client.post(
            f"/api/words?pack_id={pack['id']}",
            json={"english": "Mountain", "translations": ["гора"]},
        )
        assert created.status_code == 201
        word = created.json()
        assert (await client.get(f"/api/packs/{pack['id']}")).json()["word_ids"] == [word["id"]]

        duplicate = await client.post(
            f"/api/words?pack_id={pack['id']}",
            json={"english": "  mountain  ", "translations": ["холм"]},
        )
        assert duplicate.status_code == 409
        assert "already in the vocabulary library" in duplicate.json()["detail"]
        direct_duplicate = await client.post(
            "/api/words", json={"english": "MOUNTAIN", "translations": ["холм"]}
        )
        assert direct_duplicate.status_code == 409
        assert len((await client.get("/api/words")).json()) == 31
        assert (await client.get(f"/api/packs/{pack['id']}")).json()["word_ids"] == [word["id"]]

        other = (
            await client.post("/api/words", json={"english": "hill", "translations": ["холм"]})
        ).json()
        conflict = await client.put(
            f"/api/words/{other['id']}",
            json={"english": "MOUNTAIN", "translations": ["холм"]},
        )
        assert conflict.status_code == 409
        assert (await client.get(f"/api/words/{other['id']}")).json()["english"] == "hill"
        unchanged = await client.put(
            f"/api/words/{word['id']}",
            json={"english": "mountain", "translations": ["гора"]},
        )
        assert unchanged.status_code == 200
        assert unchanged.json()["english"] == "mountain"

        missing_pack = await client.post(
            "/api/words?pack_id=999999",
            json={"english": "summit", "translations": ["вершина"]},
        )
        assert missing_pack.status_code == 404
        assert all(word["english"] != "summit" for word in (await client.get("/api/words")).json())

    run(scenario())


def test_word_inputs_preserve_english_case_on_create_edit_and_import(client):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        created = (
            await client.post("/api/words", json={"english": " TrEe ", "translations": ["ДЕРЕВО"]})
        ).json()
        assert created["english"] == "TrEe"
        assert created["translations"] == ["дерево"]

        edited = (
            await client.put(
                f"/api/words/{created['id']}",
                json={"english": "RIVER", "translations": ["РЕКА"]},
            )
        ).json()
        assert edited["english"] == "RIVER"
        assert edited["translations"] == ["река"]

        content = "english,translations\nLANTERN,ФОНАРЬ\n".encode()
        preview = (
            await client.post("/api/import/preview", files={"file": ("words.csv", content)})
        ).json()
        assert preview["rows"][0]["data"]["english"] == "LANTERN"
        assert preview["rows"][0]["data"]["translations"] == ["фонарь"]
        imported = (await client.post("/api/import", files={"file": ("words.csv", content)})).json()
        assert imported["imported"] == 1
        assert any(word["english"] == "LANTERN" for word in (await client.get("/api/words")).json())

    run(scenario())


def test_csv_preview_duplicate_validation_and_russian(client):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        content = "english,translations,ipa\ncat,кошка,/kæt/\nhello,привет; здравствуй,/həˈloʊ/\n"
        preview = (
            await client.post(
                "/api/import/preview", files={"file": ("words.csv", content.encode())}
            )
        ).json()
        assert preview["rows"][0]["duplicate_id"] is not None
        assert preview["rows"][1]["data"]["translations"] == ["привет", "здравствуй"]
        overlapping = (
            await client.post(
                "/api/import/preview",
                files={"file": ("more.csv", "english,translations\nCAT,кот\n".encode())},
            )
        ).json()
        assert overlapping["rows"][0]["duplicate_id"] is not None
        repeated = (
            await client.post(
                "/api/import/preview",
                files={
                    "file": ("bank.csv", "english,translations\nbank,банк\nbank,берег\n".encode())
                },
            )
        ).json()
        assert len(repeated["rows"]) == 1
        assert "repeated in this file" in repeated["errors"][0]
        imported = (
            await client.post("/api/import", files={"file": ("words.csv", content.encode())})
        ).json()
        assert imported["imported"] == 1
        exported = (await client.get("/api/export")).text
        assert "привет; здравствуй" in exported
        bad = (
            await client.post(
                "/api/import/preview",
                files={"file": ("bad.csv", b"english,translations\nmissing,\n")},
            )
        ).json()
        assert bad["errors"]
        extra = (
            await client.post(
                "/api/import/preview",
                files={"file": ("extra.csv", b"english,translations\nword,translation,extra\n")},
            )
        ).json()
        assert "too many columns" in extra["errors"][0]

    run(scenario())


def test_login_rate_limit():
    key = "test-rate-limit"
    clear_failed_logins(key)
    for _ in range(5):
        assert login_allowed(key)
        record_failed_login(key)
    assert not login_allowed(key)
    clear_failed_logins(key)


def test_picture_upload_validation_and_media(client):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        word = (
            await client.post("/api/words", json={"english": "tree", "translations": ["дерево"]})
        ).json()
        bad = await client.post(
            f"/api/words/{word['id']}/picture",
            files={"file": ("bad.png", b"not an image", "image/png")},
        )
        assert bad.status_code == 400
        image = Image.new("RGB", (800, 500), "green")
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        uploaded = await client.post(
            f"/api/words/{word['id']}/picture",
            files={"file": ("tree.png", buffer.getvalue(), "image/png")},
        )
        assert uploaded.status_code == 200
        picture = uploaded.json()["picture"]
        served = await client.get(picture)
        assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
        with Image.open(io.BytesIO(served.content)) as thumbnail:
            assert max(thumbnail.size) == 640

    run(scenario())
