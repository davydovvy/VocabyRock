import io
import json
import wave
import zipfile
from uuid import uuid4

from app.models import Word

from .conftest import run


def wav_bytes(sample: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(24000)
        recording.writeframes(sample.to_bytes(2, "little", signed=True) * 2400)
    return output.getvalue()


def test_pack_audio_export_upload_and_archive_roundtrip(client, database):
    async def scenario():
        child_id = next(
            p["id"] for p in (await client.get("/api/profiles")).json() if p["role"] == "child"
        )
        await client.post("/api/auth/child", json={"user_id": child_id})
        assert (await client.get("/api/packs/1/audio-generation")).status_code == 403
        assert (
            await client.post("/api/packs/1/audio", files={"files": ("x.wav", wav_bytes(1))})
        ).status_code == 403
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})

        first = (
            await client.post(
                "/api/words",
                json={"english": "Lantern", "translations": ["фонарь"], "ipa": "/ˈlæntərn/"},
            )
        ).json()
        second = (
            await client.post(
                "/api/words", json={"english": "River", "translations": ["река"], "ipa": "/ˈrɪvər/"}
            )
        ).json()
        pack = (await client.post("/api/packs", json={"name": "Audio Travel"})).json()
        await client.put(
            f"/api/packs/{pack['id']}/words", json={"word_ids": [second["id"], first["id"]]}
        )

        exported = await client.get(f"/api/packs/{pack['id']}/audio-generation")
        assert exported.status_code == 200
        assert "attachment" in exported.headers["content-disposition"]
        payload = exported.json()
        assert payload["format"] == "vacabyrock-audio-generation"
        assert payload["pack"] == {"guid": pack["guid"], "name": pack["name"]}
        assert payload["voice"] == "af_heart"
        assert payload["takes_per_word"] == 3
        assert [word["guid"] for word in payload["words"]] == [second["guid"], first["guid"]]

        good = wav_bytes(123)
        other = wav_bytes(456)
        files = [
            ("files", (f"{first['guid']}--lantern--af_heart--take01.wav", good, "audio/wav")),
            ("files", (f"{first['guid']}--lantern--af_heart--take02.wav", other, "audio/wav")),
            ("files", (f"{second['guid']}--river--af_heart--take03.wav", other, "audio/wav")),
        ]
        uploaded = await client.post(f"/api/packs/{pack['id']}/audio", files=files)
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json() == {"imported": 2, "duplicates": 1}
        saved = (await client.get(f"/api/words/{first['id']}")).json()
        played = await client.get(saved["audio"])
        assert played.headers["content-type"] == "audio/wav"
        assert played.content == good

        archive = await client.get("/api/library/archive")
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            manifest = json.loads(zipped.read("manifest.json"))
            archived = next(word for word in manifest["words"] if word["guid"] == first["guid"])
            assert archived["audio"].endswith(".wav")
            assert zipped.read(archived["audio"]) == good
        restored = await client.post(
            "/api/library/archive",
            files={"file": ("backup.zip", archive.content, "application/zip")},
        )
        assert restored.status_code == 200, restored.text
        with database() as db:
            word = db.get(Word, first["id"])
            assert word.guid == first["guid"]
            restored_audio = word.audio
        assert (await client.get(restored_audio)).content == good

    run(scenario())


def test_pack_audio_rejects_foreign_guid_and_invalid_wav_without_changes(client):
    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        pack = (await client.get("/api/packs")).json()[0]
        word = (await client.get(f"/api/words/{pack['word_ids'][0]}")).json()
        before = word["audio"]
        foreign = await client.post(
            f"/api/packs/{pack['id']}/audio",
            files={"files": (f"{uuid4()}--foreign--take01.wav", wav_bytes(1), "audio/wav")},
        )
        assert foreign.status_code == 400
        invalid = await client.post(
            f"/api/packs/{pack['id']}/audio",
            files={"files": (f"{word['guid']}--word--take01.wav", b"not a wav", "audio/wav")},
        )
        assert invalid.status_code == 400
        truncated = await client.post(
            f"/api/packs/{pack['id']}/audio",
            files={"files": (f"{word['guid']}--word--take01.wav", wav_bytes(1)[:-2], "audio/wav")},
        )
        assert truncated.status_code == 400
        invalid_second_take = await client.post(
            f"/api/packs/{pack['id']}/audio",
            files=[
                ("files", (f"{word['guid']}--word--take01.wav", wav_bytes(1), "audio/wav")),
                ("files", (f"{word['guid']}--word--take02.wav", b"not a wav", "audio/wav")),
            ],
        )
        assert invalid_second_take.status_code == 400
        assert (await client.get(f"/api/words/{word['id']}")).json()["audio"] == before

    run(scenario())
