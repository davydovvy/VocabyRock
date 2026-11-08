import io
import json
import zipfile
from uuid import uuid4

from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.models import Pack, PracticeSession, Progress, Word

from .conftest import run


def _picture() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (80, 60), "orange").save(output, "PNG")
    return output.getvalue()


def test_archive_replaces_library_and_preserves_matching_progress(client, database):
    async def scenario():
        profiles = (await client.get("/api/profiles")).json()
        child = next(profile for profile in profiles if profile["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        assert (await client.get("/api/library/archive")).status_code == 403
        assert (
            await client.post(
                "/api/library/archive/inspect", files={"file": ("library.zip", b"test")}
            )
        ).status_code == 403
        assert (
            await client.post("/api/library/archive", files={"file": ("library.zip", b"test")})
        ).status_code == 403
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})

        word = (
            await client.post(
                "/api/words",
                json={
                    "english": "Lantern",
                    "translations": ["фонарь"],
                    "ipa": "/ˈlæntərn/",
                    "part_of_speech": "noun",
                    "example_en": "Carry a lantern.",
                    "example_ru": "Неси фонарь.",
                    "notes": "A light",
                },
            )
        ).json()
        pack = (
            await client.post(
                "/api/packs", json={"name": "Travel", "description": "Trips", "category": "Places"}
            )
        ).json()
        await client.put(f"/api/packs/{pack['id']}/words", json={"word_ids": [word["id"]]})
        await client.post(
            f"/api/words/{word['id']}/picture",
            files={"file": ("lantern.png", _picture(), "image/png")},
        )
        await client.post(
            f"/api/packs/{pack['id']}/cover",
            files={"file": ("travel.png", _picture(), "image/png")},
        )
        audio_bytes = b"ID3" + b"test pronunciation"
        audio_file = get_settings().data_dir / "audio" / "lantern.mp3"
        audio_file.parent.mkdir(parents=True, exist_ok=True)
        audio_file.write_bytes(audio_bytes)
        with database() as db:
            stored = db.get(Word, word["id"])
            stored.audio = "/audio/lantern.mp3"
            db.add(
                Progress(
                    user_id=child["id"],
                    word_id=word["id"],
                    direction="en-ru",
                    attempts=7,
                    correct=5,
                    incorrect=2,
                    interval_days=3,
                    status="review",
                )
            )
            session = PracticeSession(
                user_id=child["id"],
                pack_id=pack["id"],
                mode="all",
                kind="choice",
                direction="en-ru",
                tasks=[],
                results=[],
            )
            db.add(session)
            db.commit()
            session_id = session.id

        exported = await client.get("/api/library/archive")
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            archived_word = next(item for item in manifest["words"] if item["guid"] == word["guid"])
            archived_pack = next(item for item in manifest["packs"] if item["guid"] == pack["guid"])
            assert archived_word["ipa"] == "/ˈlæntərn/"
            assert archive.read(archived_word["audio"]) == audio_bytes
            assert archive.read(archived_word["picture"])
            assert archive.read(archived_pack["cover"])
            assert archived_pack["word_guids"] == [word["guid"]]

        original_picture = (await client.get(f"/api/words/{word['id']}")).json()["picture"]
        seed_word = next(item for item in manifest["words"] if item["guid"] != word["guid"])
        seed_pack = next(item for item in manifest["packs"] if item["guid"] != pack["guid"])
        with database() as db:
            seed_word_id = db.scalar(select(Word.id).where(Word.guid == seed_word["guid"]))
            seed_pack_id = db.scalar(select(Pack.id).where(Pack.guid == seed_pack["guid"]))
        await client.delete(f"/api/packs/{seed_pack_id}")
        await client.delete(f"/api/words/{seed_word_id}")

        with database() as db:
            db.get(Word, word["id"]).guid = str(uuid4())
            db.get(Word, word["id"]).translations = ["неверно"]
            db.get(Pack, pack["id"]).guid = str(uuid4())
            db.get(Pack, pack["id"]).description = "Changed"
            extra = Word(english="Discard me", translations=["удалить"])
            db.add(extra)
            db.flush()
            db.add(
                Progress(
                    user_id=child["id"],
                    word_id=extra.id,
                    direction="en-ru",
                    attempts=2,
                    correct=1,
                    incorrect=1,
                )
            )
            db.commit()
            extra_id = extra.id
            extra_guid = extra.guid

        upload = {"file": ("library.zip", exported.content, "application/zip")}
        preview = await client.post("/api/library/archive/inspect", files=upload)
        assert preview.status_code == 200
        assert preview.json() == {"words": len(manifest["words"]), "packs": len(manifest["packs"])}
        imported = await client.post("/api/library/archive", files=upload)
        assert imported.status_code == 200, imported.text
        assert imported.json() == preview.json()
        with database() as db:
            restored_word = db.get(Word, word["id"])
            restored_pack = db.get(Pack, pack["id"])
            assert restored_word.guid == word["guid"]
            assert restored_word.translations == ["фонарь"]
            assert restored_word.example_en == "Carry a lantern."
            assert restored_pack.guid == pack["guid"]
            assert restored_pack.description == "Trips"
            assert [item.word_id for item in restored_pack.words] == [word["id"]]
            assert db.scalar(select(Word).where(Word.guid == extra_guid)) is None
            assert db.scalar(select(Progress).where(Progress.word_id == extra_id)) is None
            assert db.scalar(select(Word).where(Word.guid == seed_word["guid"]))
            assert db.scalar(select(Pack).where(Pack.guid == seed_pack["guid"]))
            progress = db.scalar(
                select(Progress).where(
                    Progress.user_id == child["id"], Progress.word_id == word["id"]
                )
            )
            assert progress.attempts == 7
            assert progress.status == "review"
            assert db.get(PracticeSession, session_id).pack_id == pack["id"]
            picture_path = restored_word.picture
            cover_path = restored_pack.cover
            audio_path = restored_word.audio
        assert (await client.get(picture_path)).status_code == 200
        assert (await client.get(original_picture)).status_code == 404
        assert (await client.get(cover_path)).status_code == 200
        assert (await client.get(audio_path)).content == audio_bytes

        assert (await client.post("/api/library/archive", files=upload)).status_code == 200
        with database() as db:
            assert db.get(Word, word["id"]).guid == word["guid"]
            assert db.scalar(select(Progress).where(Progress.word_id == word["id"])).attempts == 7

    run(scenario())


def test_archive_rejects_invalid_files_without_changing_library(client, database):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        original_words = (await client.get("/api/words")).json()
        assert (
            await client.post(
                "/api/library/archive/inspect", files={"file": ("bad.zip", b"not a zip")}
            )
        ).status_code == 400
        assert (
            await client.post("/api/library/archive", files={"file": ("bad.zip", b"not a zip")})
        ).status_code == 400

        exported = await client.get("/api/library/archive")
        with zipfile.ZipFile(io.BytesIO(exported.content)) as source:
            manifest = json.loads(source.read("manifest.json"))
        manifest["words"][0]["picture"] = "media/images/missing.webp"
        invalid = io.BytesIO()
        with zipfile.ZipFile(invalid, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
        assert (
            await client.post(
                "/api/library/archive",
                files={"file": ("bad.zip", invalid.getvalue(), "application/zip")},
            )
        ).status_code == 400
        assert (await client.get("/api/words")).json() == original_words
        assert (await client.get("/api/import")).status_code == 404
        assert (await client.get("/api/export")).status_code == 404
        with database() as db:
            assert db.scalar(select(Word).where(Word.guid == original_words[0]["guid"]))

    run(scenario())


def test_archive_without_audio_keeps_existing_recordings_for_matching_words(client, database):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        word = (
            await client.post("/api/words", json={"english": "Lantern", "translations": ["фонарь"]})
        ).json()
        audio_bytes = b"ID3" + b"uploaded pronunciation"
        audio_file = get_settings().data_dir / "audio" / "uploaded-lantern.mp3"
        audio_file.parent.mkdir(parents=True, exist_ok=True)
        audio_file.write_bytes(audio_bytes)
        with database() as db:
            stored = db.get(Word, word["id"])
            stored.audio = "/audio/uploaded-lantern.mp3"
            db.commit()

        exported = await client.get("/api/library/archive")
        with zipfile.ZipFile(io.BytesIO(exported.content)) as source:
            manifest = json.loads(source.read("manifest.json"))
            matching = next(item for item in manifest["words"] if item["guid"] == word["guid"])
            audio_entry = matching["audio"]
            matching["audio"] = None
            matching.update(
                {
                    "audio_source_url": "https://upload.wikimedia.org/old.mp3",
                    "audio_status": "pending",
                    "audio_attempts": 2,
                    "audio_next_attempt_at": None,
                    "audio_error": None,
                }
            )
            without_audio = io.BytesIO()
            with zipfile.ZipFile(without_audio, "w") as archive:
                for name in source.namelist():
                    if name == "manifest.json":
                        archive.writestr(name, json.dumps(manifest))
                    elif name != audio_entry:
                        archive.writestr(name, source.read(name))

        imported = await client.post(
            "/api/library/archive",
            files={"file": ("library.zip", without_audio.getvalue(), "application/zip")},
        )
        assert imported.status_code == 200, imported.text
        restored = (await client.get(f"/api/words/{word['id']}")).json()
        assert restored["audio"] == "/audio/uploaded-lantern.mp3"
        assert (await client.get(restored["audio"])).content == audio_bytes
        assert audio_file.read_bytes() == audio_bytes
        reexported = await client.get("/api/library/archive")
        with zipfile.ZipFile(io.BytesIO(reexported.content)) as archive:
            next_manifest = json.loads(archive.read("manifest.json"))
            next_word = next(
                item for item in next_manifest["words"] if item["guid"] == word["guid"]
            )
            assert "audio_status" not in next_word
            assert "audio_source_url" not in next_word

    run(scenario())
