# VacabyRock

VacabyRock is a family vocabulary adventure for two children learning English and Russian. Children choose an animal avatar, play five games, and earn stars. A password protected parent area manages words, packs, pictures, settings, and progress. All interface text is in English; Russian appears as learning content.

## Architecture

- React, TypeScript, Vite, and Tailwind CSS build a responsive single page app.
- FastAPI serves the compiled app and REST API from the same origin.
- SQLite stores users, shared vocabulary, packs, sessions, settings, and each child's progress by word and direction. Each word and pack has a stable GUID for portable vocabulary archives. SQLAlchemy models and Alembic migrations manage the schema.
- Uploaded and selected Pixabay images are validated, resized, and kept on the local data volume. A selected Wikimedia pronunciation is downloaded to the same volume for offline playback; browser speech synthesis is the fallback for words without a recording.
- One container runs FastAPI. Docker Compose bind mounts one persistent directory.

## Repository layout

| Path | Purpose |
| --- | --- |
| `backend/app/` | API, authentication, models, practice logic, imports, and seed data |
| `backend/alembic/` | Database migrations |
| `backend/tests/` | Backend unit and API tests |
| `frontend/src/` | React app, Colorful Adventure styles, and UI tests |
| `frontend/e2e/` | Browser smoke and iPad layout tests |
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

If the NAS cannot download build dependencies and it has the same CPU architecture as your laptop, build the app on the laptop and transfer the image file to the Synology project folder. Run `docker compose build` and `docker save -o vacabyrock-image.tar vacabyrock:local` on the laptop. On the NAS, use the updated `docker-compose.yml` and your existing `.env`, then run `sudo docker load -i vacabyrock-image.tar` and `sudo docker compose up -d --no-build`. The app applies database migrations when it starts. Keep the existing Synology data directory and make a backup before the update.

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

The browser tests use a running app with fresh demo content. The smoke test adds one test word; the landscape tests check game layout and Big Match dragging:

```sh
cd frontend
BASE_URL=http://127.0.0.1:8787 ADMIN_PASSWORD=your-password npm run test:e2e
```

It selects a child, plays through a pack, checks the result, signs in as the parent, adds a word, and finds it in the child's library. Set `CHROMIUM_PATH` if Chromium is installed elsewhere.

## Parent workflow

Choose the locked Parent avatar and enter `ADMIN_PASSWORD`. In **Settings → Children**, change a child's name beside their avatar and click **Save**. Add words to the library with one or more Russian translations and optional IPA. **Part of speech** is a dropdown that starts blank. English words keep their typed capitalization; Russian translations become lowercase. **Fill from Wikimedia** searches without regard to capitalization and replaces the English field with the dictionary's spelling when it finds an entry. In **Add Word** or **Edit Word**, upload a JPEG, PNG, or WebP picture (up to 8 MB), or choose one from Pixabay, then click **Save Word**. Vocabulary cards use a responsive grid and show the picture, English word, IPA, and translations, with edit and delete icons on the right. The server checks and resizes saved pictures to local WebP files. Create packs, open **Manage Words**, and use **New Word** to create a word directly in that pack or the pencil button to edit one of its words. Pack word lists also show pictures and IPA. Existing library words can still be added to multiple packs. A word already in the library cannot be created again under a different capitalization or translation; choose it from the existing-word list instead. Deleting a pack keeps its words in the library.

In **Vocabulary** and a pack's **Manage Words** list, each word has a checkbox labeled with each child's name. Check it to mark the word learned for that child, or uncheck it to mark the word unlearned. The two children have independent progress, and changing a checkbox keeps the word's practice counts. Unchecking also resets that word's correct typing streak. The same learned state appears in both lists and in the Progress area.

To search Pixabay for a word picture, add your API key as `PIXABAY_API_KEY` in `.env` and run `docker compose up -d --build` to apply it. In the word form, use **Search Pixabay**, choose a picture, and click **Save Word**. The key stays on the server. Search results show their Pixabay source; temporary thumbnails are fetched by the server from the image URL in the search result and shown from the app's own address, so the browser does not need direct access to Pixabay's image CDN. The chosen preview is then read from the local cache, validated, and saved as the word's picture before children see it. Pixabay search needs internet access. API responses and temporary thumbnails are cached for 24 hours in `data/pixabay-cache/`. See [Pixabay's API documentation](https://pixabay.com/api/docs/) and [Content License](https://pixabay.com/service/terms/) for its current requirements.

When adding a word with a picture, **Save Word** creates the word first and then attaches the picture. If the picture step fails, the form stays open as **Edit Word**; fix the issue and click **Save Word** again. This retries the picture without creating a duplicate word.

### Removing a word picture

In the parent area, open **Vocabulary** and click the pencil icon for the word. You can also open a pack's **Manage Words** list and edit the word there. In **Edit Word**, click **Remove picture**; the preview becomes empty. Click **Save Word** to remove the picture without changing or deleting the word. To cancel before saving, click **Keep current picture** or close the form.

After saving, the picture is cleared everywhere the word appears, including pack lists and printable sheets. The stored image file is deleted. For API clients, `DELETE /api/words/{word_id}/picture` requires parent authentication and returns `{"picture": null}`; repeating it when the word has no picture is safe.

### Dictionary lookup and pronunciation

In **Add Word** or **Edit Word**, enter the English word and click **Fill from Wikimedia**. Typing alone sends no lookup requests. The button queries [WiktAPI](https://wiktapi.dev/quickstart) for Russian translation choices, IPA, part of speech, and available recordings. US pronunciations appear first; if the entry lists a US spelling, the form offers it. Select translations and a recording, then review the visible fields before saving. Missing information stays blank for manual entry.

Saving creates the word immediately. If a recording was selected, the library shows **Audio queued for download**, **Audio retry scheduled**, or an error with **Retry audio** while the download is pending or has failed. Once a recording is saved, a speaker button appears beside the word in both **Vocabulary** and the pack's **Manage Words** list; click it to hear the locally stored pronunciation. A single background worker downloads recordings to the Synology data volume and resumes pending work after a restart. It spaces downloads and honors Wikimedia's `Retry-After` response; a rate limit can delay audio without losing the word. After eight unsuccessful attempts, use **Retry audio** to queue it again. The child's Listen game uses the saved recording offline, falling back to browser speech synthesis when no recording is stored.

The lookup needs access to `api.wiktapi.dev`; audio downloads need access to `upload.wikimedia.org`. No dictionary API key is required. Wikimedia does not promise a fixed download quota and says limits can change; the app waits and retries when it receives a limit response. See [Wikimedia's API usage guidelines](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines).

The **Import / Export** area downloads one ZIP vocabulary archive containing all words, packs, pack membership and order, pictures, pack covers, IPA transcriptions, notes, examples, and downloaded pronunciation files. On the laptop, finish editing and download the archive. On Synology, upload it, click **Check archive**, then **Replace library**. The archive is validated before changes are made. Import replaces all destination words and packs, including their media. Child profiles, settings, stars, and progress stay on the destination. A word or pack with the same GUID keeps its database ID; on the first transfer from an independently installed library, a matching English word or pack name adopts the archive GUID. This preserves learning progress for matching words. Progress for words omitted from the archive is removed. Reimporting the same archive is safe. This vocabulary archive is distinct from the full database backup below, which also includes profiles and progress.

The Progress area shows both children independently, including learned and difficult words, success rates, recent games, and upcoming reviews. It can reset one word, one pack, or all progress for one child with confirmation. API clients can set a child's learned state with parent authentication using `PUT /api/progress/learned` and a JSON body containing `child_id`, `word_id`, and `learned` (a Boolean).

In **Word Packs**, the parent can download two A4 PDFs for any pack. **Word sheet** fits pictures, English words, transcriptions, and Russian translations into compact columns. **Writing test** shows each picture and Russian translation with a line for the child to write the English word. Both include every word in the pack and use the pack's current order. If a word has no saved picture, its image space is left blank.

## Learning and settings

Children can choose **Study** on a pack to select New Words, Practice, Hard Words, or All Words, then choose Big Match, Flip Cards, Pick the Word, Type It, or Listen. **Test** asks for the English spelling of every word in that pack that is not yet learned; it uses keyboard entry and offers no hints. A child learns a word after typing its English spelling correctly twice in a row without hints. A wrong spelling resets that word's streak. Case and extra spaces do not matter, but the optional typo tolerance does not count toward learning. Choices, cards, and matching still provide practice without marking words learned. A pack is learned once at least 90% of its words are learned. The parent can set game length, default direction, American or British speech, exercise availability, handling of Russian `е`/`ё`, optional one letter typo tolerance, and avatar choice. All settings persist in SQLite.

### Big Match

Big Match is the only matching game in the child menu. It presents eight English cards in a fixed 4 × 2 grid above eight shuffled Russian tiles. Drag a tile onto any part of an English card, or tap the tile and then the card. Drag a placed tile to another card to change its match; a displaced tile returns to its original place in the pool. Drag a tile back to the pool to remove it. **Reset** clears the movable placements.

The game gives no right or wrong hints while placing tiles. **Check** becomes available after all eight cards are filled. Correct pairs turn green and lock; incorrect pairs turn orange and remain movable. Fill any emptied cards and check again until all eight are correct. **Play Again** and **Home** appear on the results screen.

The first Check alone sets the score, XP, stars, and review progress. Later correction checks do not create more attempts or rewards. Progress is tracked separately for each child. Big Match always asks English to Russian, uses eight distinct English words with uniquely matchable Russian translations, and ignores the general session length setting. If the chosen pack and mode cannot provide eight suitable words, the child sees a message to try another pack or mode. Earlier matching sessions remain in historical records, but the retired games cannot be started from the menu.

In Type It, transcriptions are hidden. The first hint shows the first and last letters, such as `M----y` for Monday, without counting as a mistake. The second reveals the whole answer and immediately adds that word to mistakes for later practice. After checking an answer, Enter advances to **Next**. Both directions are available for the other games.

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
- Pixabay search needs an API key and internet access. The app downloads the selected 150 px preview and saves it locally; if Pixabay limits that download, the app retries briefly and may ask you to try again later.
- Spaced repetition is deliberately simple and is not a formal language proficiency assessment.
