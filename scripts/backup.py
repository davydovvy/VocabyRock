"""Create a SQLite-consistent ZIP with database and locally stored media."""
import argparse
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def backup(data_dir: Path, output: Path):
    database = data_dir / "vacabyrock.sqlite3"
    if not database.is_file():
        raise SystemExit(f"Database not found: {database}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        snapshot = Path(temp) / "vacabyrock.sqlite3"
        with sqlite3.connect(database) as source, sqlite3.connect(snapshot) as destination:
            source.backup(destination)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "vacabyrock.sqlite3")
            for directory in ("images", "audio"):
                for path in (data_dir / directory).rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(data_dir))
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    destination = arguments.output or arguments.data / "backups" / f"vacabyrock-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip"
    backup(arguments.data, destination)
