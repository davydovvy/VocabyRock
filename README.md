# VacabyRock

VacabyRock is a family vocabulary adventure for two children learning English and Russian. Children choose an animal avatar, play five short games, and earn stars. A password protected parent area manages words, packs, pictures, settings, and progress. All interface text is in English; Russian appears as learning content.

## Architecture

- React, TypeScript, Vite, and Tailwind CSS build a responsive single page app.
- FastAPI serves the compiled app and REST API from the same origin.
- SQLite stores users, shared vocabulary, packs, sessions, settings, and each child's progress by word and direction. SQLAlchemy models and Alembic migrations manage the schema.
- Uploaded and selected Pixabay images are validated, resized, and kept on the local data volume. A selected Wikimedia pronunciation is downloaded to the same volume for offline playback; browser speech synthesis is the fallback for words without a recording.
- One container runs FastAPI. Docker Compose bind mounts one persistent directory.

## Repository layout

| Path | Purpose |
| --- | --- |
| `backend/app/` | API, authentication, models, practice logic, imports, and seed data |
| `backend/alembic/` | Database migrations |
| `backend/tests/` | Backend unit and API tests |
| `frontend/src/` | React app, Colorful Adventure styles, and UI tests |
| `frontend/e2e/` | Browser smoke test |
| `scripts/` | Backup and restore tools |
| `data/` | Local development data; ignored by Git |

## Quick start with Docker Compose

1. Copy `.env.example` to `.env`. Set a strong `ADMIN_PASSWORD` and choose a writable `DATA_PATH`.
2. Create the data directory and make it writable by the container user. On a Linux laptop, run `mkdir -p data` and set `PUID` and `PGID` in `.env` to the output of `id -u` and `id -g`. Alternatively, keep the default UID/GID `10001:10001` and run `sudo chown -R 10001:10001 data`.
3. Run `docker compose up -d --build`.
4. Open `http://localhost:8787` or `http://diskstation.local:8787` from a device on the same LAN.
5. Check `docker compose ps` or `http://localhost:8787/api/health` if startup takes a moment.

On first startup, VacabyRock creates the parent profile, two child profiles, and Animals, Food, and Everyday Objects packs with 30 sample words. Later restarts keep all data. The initial parent password is read from `.env`; the example placeholder does not grant access.

The first Docker build downloads build dependencies. Parent picture searches, dictionary lookups, and pronunciation downloads need internet access. Once a recording is ready, children can play it without internet access. Words without a saved recording use the device's English speech voice when available.

## Synology DiskStation

Put this project in a Synology folder, then set `DATA_PATH=/volume1/docker/vacabyrock/data` in `.env`. Create that directory through SSH or File Station. Give the UID/GID set by `PUID` and `PGID` read/write access to it; the defaults are `10001:10001`. For example, from SSH with sufficient privileges:

```sh
sudo mkdir -p /volume1/docker/vacabyrock/data
sudo chown -R 10001:10001 /volume1/docker/vacabyrock/data
docker compose up -d --build
```

If you use a different Synology user ID, set `PUID` and `PGID` to that owner's IDs. Allow the chosen port through the DiskStation firewall. The app is intended for a trusted family LAN: child login is intentionally passwordless. If you expose it beyond the LAN, put it behind HTTPS and additional network access controls, then set `COOKIE_SECURE=true`.

## Development

Use Python 3.11 or newer, Node.js 22 or newer, and `uv` for Python dependency installation. From the repository root:

```sh
cp .env.example .env
python3 -m venv .venv
uv pip install --python .venv/bin/python -e './backend[dev]'
mkdir -p data/images data/audio
cd backend
DATA_DIR=../data ../.venv/bin/alembic upgrade head
DATA_DIR=../data ../.venv/bin/python -m app.initialize
DATA_DIR=../data FRONTEND_DIST=../frontend/dist ADMIN_PASSWORD=your-local-password ../.venv/bin/uvicorn app.main:app --reload --port 8000
```

In another terminal, run `cd frontend && npm ci && npm run dev`. Open `http://localhost:5173`; Vite forwards `/api`, `/media`, and `/audio` to port 8000. Set `ADMIN_PASSWORD` and, if using Pixabay, `PIXABAY_API_KEY` in the backend terminal (or run from the repository root where `.env` is read). Keep `.env` and `data/` private.

### Tests and checks

```sh
cd backend && ../.venv/bin/python -m pytest tests -q && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
cd frontend && npm run test && npm run lint && npm run format:check && npm run build
docker compose build
```

The browser smoke test uses a running app with fresh demo content and adds one test word:

```sh
cd frontend
BASE_URL=http://127.0.0.1:8787 ADMIN_PASSWORD=your-password npm run test:e2e
```

It selects a child, plays through a pack, checks the result, signs in as the parent, adds a word, and finds it in the child's library. Set `CHROMIUM_PATH` if Chromium is installed elsewhere.

## Parent workflow

Choose the locked Parent avatar and enter `ADMIN_PASSWORD`. Add words to the library with one or more Russian translations, optional IPA, examples, and notes. Upload JPEG, PNG, or WebP pictures (up to 8 MB); the server checks and resizes them to local WebP files. Create packs, add existing words to multiple packs, and move words up or down. Deleting a pack keeps its words in the library.

To search Pixabay for a word picture, add your API key as `PIXABAY_API_KEY` in `.env` and run `docker compose up -d --build` to apply it. In the parent's Vocabulary Library, use the **Pixabay** button beside a word, search, and choose a picture. The key stays on the server. Search results show their Pixabay source; a chosen picture is downloaded, validated, and saved locally before children see it. Pixabay search needs internet access. API responses are cached for 24 hours in `data/pixabay-cache/`. See [Pixabay's API documentation](https://pixabay.com/api/docs/) and [Content License](https://pixabay.com/service/terms/) for its current requirements.

### Dictionary lookup and pronunciation

In **Add Word** or **Edit Word**, enter the English word and click **Fill from Wikimedia**. Typing alone sends no lookup requests. The button queries [WiktAPI](https://wiktapi.dev/quickstart) for Russian translation choices, IPA, and available recordings. US pronunciations appear first; if the entry lists a US spelling, the form offers it. Select translations and a recording, then review or edit every field before saving. Missing information stays blank for manual entry.

Saving creates the word immediately. If a recording was selected, the library shows **Audio queued for download**, **Audio retry scheduled**, **Audio available offline**, or an error with **Retry audio**. A single background worker downloads recordings to the Synology data volume and resumes pending work after a restart. It spaces downloads and honors Wikimedia's `Retry-After` response; a rate limit can delay audio without losing the word. After eight unsuccessful attempts, use **Retry audio** to queue it again. The child's Listen game uses the saved recording offline, falling back to browser speech synthesis when no recording is stored.

The lookup needs access to `api.wiktapi.dev`; audio downloads need access to `upload.wikimedia.org`. No dictionary API key is required. Wikimedia does not promise a fixed download quota and says limits can change; the app waits and retries when it receives a limit response. See [Wikimedia's API usage guidelines](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines).

The Import / Export area provides a UTF-8 CSV template, preview, validation, duplicate recognition, and exports for the whole library or a pack. Separate translations in one CSV cell with semicolons. Entries with the same English text but different translations remain separate meanings.

The Progress area shows both children independently, including learned and difficult words, success rates, recent games, and upcoming reviews. It can reset one word, one pack, or all progress for one child with confirmation.

## Learning and settings

Children can choose New Words, Practice, Hard Words, or All Words in a pack, then play Find Pairs, Flip Cards, Pick the Word, Type It, or Listen. Quick Play starts a short choice game. Both directions are available. The parent can set game length, default direction, American or British speech, exercise availability, handling of Russian `е`/`ё`, optional one letter typo tolerance, and avatar choice. All settings persist in SQLite.

Correct answers lengthen review intervals; missed words return sooner. Reviews are tracked separately for each child and translation direction. XP, levels, stars, and achievements are motivational only and do not change review scheduling.

## Environment variables and storage

| Variable | Default | Purpose |
| --- | --- | --- |
| `ADMIN_PASSWORD` | required for Compose | Parent password; keep it in `.env` |
| `PORT` | `8787` | Host port |
| `DATA_PATH` | `./data` | Host bind mount for database and media |
| `PUID`, `PGID` | `10001` | Container process user and group |
| `COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `PIXABAY_API_KEY` | empty | Optional server-side key for parent picture search |

The mount contains `vacabyrock.sqlite3`, `images/`, `audio/` (downloaded pronunciation recordings), optional `pixabay-cache/`, and optional `backups/`. Audio queue status and retry times are stored in SQLite, so queued work survives a container restart. SQLite may also create temporary `-wal` and `-shm` files. Back up the data directory and `.env` separately. Do not put either in version control.

## Backup and restore

`scripts/backup.py` uses SQLite's online backup API to make a consistent database snapshot and includes image and audio files in a ZIP. It omits `pixabay-cache/`, which the app can rebuild as needed. Run it on the host with Python 3.11+ while the app is running:

```sh
python3 scripts/backup.py --data /volume1/docker/vacabyrock/data --output /volume1/backups/vacabyrock.zip
```

For a fully consistent media snapshot, stop the app before backing up. To restore, stop the container first, then run:

```sh
docker compose down
python3 scripts/restore.py /volume1/backups/vacabyrock.zip --data /volume1/docker/vacabyrock/data
sudo chown -R 10001:10001 /volume1/docker/vacabyrock/data
docker compose up -d
```

The restore tool moves the previous database and media to a timestamped `before-restore-*` directory under the data path. Check the restored app before deleting that copy.

## Updates

Create a backup, update the source, then run `docker compose up -d --build`. Startup applies Alembic migrations before serving requests. The bind mounted data survives container replacement. Keep `.env` and `DATA_PATH` when updating.

## Known limitations

- Browser speech voices vary by device. A word without a saved recording cannot be heard in the Listen game when speech synthesis is unavailable.
- Child profiles have no passwords. Keep the service on a trusted LAN.
- Pictures use uploaded files or local emoji placeholders; the sample packs do not include licensed artwork.
- Pixabay search needs an API key and internet access. If Pixabay limits image downloads, the app retries briefly and may ask you to try again later.
- Spaced repetition is deliberately simple and is not a formal language proficiency assessment.
