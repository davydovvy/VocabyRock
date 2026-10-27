import csv
import io
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PackWord, Word
from .schemas import WordInput

HEADERS = ["english", "translations", "ipa", "part_of_speech", "example_en", "example_ru", "notes"]


def export_csv(words: list[Word]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HEADERS)
    writer.writeheader()
    for word in words:
        writer.writerow(
            {
                key: "; ".join(word.translations)
                if key == "translations"
                else getattr(word, key) or ""
                for key in HEADERS
            }
        )
    return "\ufeff" + output.getvalue()


def preview_csv(text: str, db: Session):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not {"english", "translations"} <= set(reader.fieldnames):
        return {"rows": [], "errors": ["CSV needs english and translations columns"]}
    known = [
        (
            word.english.casefold().strip(),
            {translation.casefold().strip() for translation in word.translations},
            word.id,
        )
        for word in db.scalars(select(Word))
    ]
    seen: list[tuple[str, set[str]]] = []
    rows, errors = [], []
    for line, row in enumerate(reader, start=2):
        try:
            if None in row:
                errors.append(f"Line {line}: too many columns")
                continue
            values = {key: row.get(key, "") or "" for key in HEADERS}
            values["translations"] = [
                part.strip() for part in values["translations"].split(";") if part.strip()
            ]
            data = WordInput.model_validate(values)
            english = data.english.casefold()
            translations = {translation.casefold() for translation in data.translations}
            duplicate = next(
                (
                    word_id
                    for existing, meanings, word_id in known
                    if existing == english and meanings & translations
                ),
                None,
            )
            if any(existing == english and meanings & translations for existing, meanings in seen):
                errors.append(f"Line {line}: repeated in this file")
                continue
            seen.append((english, translations))
            rows.append({"line": line, "data": data.model_dump(), "duplicate_id": duplicate})
        except Exception as exc:
            errors.append(f"Line {line}: {exc}")
    return {"rows": rows, "errors": errors}


def import_csv(text: str, db: Session, pack_id: int | None):
    preview = preview_csv(text, db)
    if preview["errors"]:
        return {**preview, "imported": 0}
    imported = 0
    for row in preview["rows"]:
        if row["duplicate_id"]:
            word_id = row["duplicate_id"]
        else:
            word = Word(**row["data"])
            db.add(word)
            db.flush()
            word_id = word.id
            imported += 1
        if pack_id is not None and not db.scalar(
            select(PackWord.id).where(PackWord.pack_id == pack_id, PackWord.word_id == word_id)
        ):
            max_position = max(
                [
                    p.position
                    for p in db.scalars(select(PackWord).where(PackWord.pack_id == pack_id))
                ],
                default=-1,
            )
            db.add(PackWord(pack_id=pack_id, word_id=word_id, position=max_position + 1))
    db.commit()
    return {**preview, "imported": imported}
