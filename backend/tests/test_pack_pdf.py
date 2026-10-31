import io
import re

from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select

from app.media import save_picture_data
from app.models import Pack, PackWord, Word

from .conftest import run


def test_pack_printouts_include_pictures_and_hide_test_answers(client, database):
    with database() as db:
        pack = db.scalar(select(Pack).where(Pack.name == "Animals"))
        word = pack.words[0].word
        image = io.BytesIO()
        Image.new("RGB", (100, 80), "orange").save(image, "PNG")
        word.picture = save_picture_data(image.getvalue())
        monkey = Word(english="monkey", translations=["обезьяна"], ipa="/ˈmʌŋki/")
        db.add(monkey)
        db.flush()
        db.add(PackWord(pack_id=pack.id, word_id=monkey.id, position=10))
        db.commit()
        pack_id = pack.id

    async def scenario():
        child = next(p for p in (await client.get("/api/profiles")).json() if p["role"] == "child")
        await client.post("/api/auth/child", json={"user_id": child["id"]})
        url = f"/api/packs/{pack_id}/print"
        assert (await client.get(f"{url}/reference")).status_code == 403
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        assert (await client.get(f"{url}/unknown")).status_code == 422
        assert (await client.get("/api/packs/99999/print/reference")).status_code == 404

        reference = await client.get(f"{url}/reference")
        writing_test = await client.get(f"{url}/test")
        for response in (reference, writing_test):
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"
            assert response.headers["content-disposition"].endswith('.pdf"')
            assert response.content.startswith(b"%PDF-")
        reference_reader = PdfReader(io.BytesIO(reference.content))
        test_reader = PdfReader(io.BytesIO(writing_test.content))
        assert len(reference_reader.pages) == len(test_reader.pages) == 1
        reference_text = reference_reader.pages[0].extract_text()
        test_text = test_reader.pages[0].extract_text()
        assert "Animals" in reference_text
        assert "cat" in reference_text
        assert "/kæt/" in reference_text
        assert "кошка" in reference_text
        assert "monkey" in reference_text
        assert "кошка" in test_text
        assert "обезьяна" in test_text
        assert "cat" not in test_text
        assert "monkey" not in test_text
        assert "/kæt/" not in test_text
        assert "Animals" not in test_text
        for reader in (reference_reader, test_reader):
            xobjects = reader.pages[0]["/Resources"].get("/XObject", {})
            assert any(item.get_object().get("/Subtype") == "/Image" for item in xobjects.values())

    run(scenario())


def test_pack_sheets_paginate_without_losing_words(client, database):
    with database() as db:
        pack = db.scalar(select(Pack).where(Pack.name == "Animals"))
        for index in range(60):
            word = Word(
                english=f"extra word {index:02d}",
                translations=[f"дополнительное слово {index:02d}"],
                ipa="/ˈek.strə/",
            )
            db.add(word)
            db.flush()
            db.add(PackWord(pack_id=pack.id, word_id=word.id, position=10 + index))
        db.commit()
        pack_id = pack.id

    async def scenario():
        await client.post("/api/auth/parent", json={"password": "test-parent-password"})
        for variant in ("reference", "test"):
            response = await client.get(f"/api/packs/{pack_id}/print/{variant}")
            assert response.status_code == 200
            reader = PdfReader(io.BytesIO(response.content))
            assert len(reader.pages) > 1
            text = "\n".join(page.extract_text() for page in reader.pages)
            assert re.search(r"дополнительное слово\s+00", text)
            assert re.search(r"дополнительное слово\s+59", text)
            if variant == "reference":
                assert "extra word 00" in text
                assert "extra word 59" in text
            else:
                assert "extra word 00" not in text
                assert "extra word 59" not in text

    run(scenario())
