"""Restore a backup while the application is stopped. Existing data is copied aside."""
import argparse
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def restore(archive_path: Path, data_dir: Path):
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts or path.parts[0] not in {"vacabyrock.sqlite3", "images", "audio"}:
                    raise SystemExit("Unsafe backup archive")
            archive.extractall(stage)
        if not (stage / "vacabyrock.sqlite3").is_file():
            raise SystemExit("Backup has no database")
        data_dir.mkdir(parents=True, exist_ok=True)
        previous = data_dir / f"before-restore-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        previous.mkdir()
        for name in ("vacabyrock.sqlite3", "vacabyrock.sqlite3-wal", "vacabyrock.sqlite3-shm", "images", "audio"):
            current = data_dir / name
            if current.exists():
                shutil.move(current, previous / name)
        for name in ("vacabyrock.sqlite3", "images", "audio"):
            source = stage / name
            if source.exists():
                shutil.move(source, data_dir / name)
    print(f"Restored {archive_path}. Previous data: {previous}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data"))
    arguments = parser.parse_args()
    restore(arguments.archive, arguments.data)
