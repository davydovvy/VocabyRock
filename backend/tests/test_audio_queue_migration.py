from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Word


def test_removing_queue_columns_preserves_stored_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    database_path = tmp_path / "vacabyrock.sqlite3"
    command.upgrade(config, "0005")

    recording = tmp_path / "audio" / "recording.wav"
    recording.parent.mkdir()
    recording.write_bytes(b"RIFFtestWAVE")
    engine = create_engine(f"sqlite:///{database_path}")
    with Session(engine) as db:
        word = Word(english="tree", translations=["дерево"], audio="/audio/recording.wav")
        db.add(word)
        db.commit()
        word_id = word.id
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE words SET audio_status = 'pending' WHERE id = :word_id"),
            {"word_id": word_id},
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    assert "audio_status" not in {column["name"] for column in inspect(engine).get_columns("words")}
    with Session(engine) as db:
        assert db.get(Word, word_id).audio == "/audio/recording.wav"
    assert recording.read_bytes() == b"RIFFtestWAVE"
    engine.dispose()
    get_settings.cache_clear()
