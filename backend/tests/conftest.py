import asyncio
import os

import anyio.to_thread
import httpx
import pytest
from sqlalchemy.orm import sessionmaker

os.environ["ADMIN_PASSWORD"] = "test-parent-password"
os.environ["DATA_DIR"] = "/tmp/vacabyrock-tests-bootstrap"

from app.config import get_settings  # noqa: E402
from app.db import Base, get_db, make_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-parent-password")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    engine = make_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        seed(db)

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield session_factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(database, monkeypatch):
    # This runner's sandbox does not wake AnyIO worker threads; keep API tests deterministic.
    async def direct_run(func, *args, **kwargs):
        return func(*args)

    monkeypatch.setattr(anyio.to_thread, "run_sync", direct_run)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    yield client
    asyncio.run(client.aclose())


def run(coroutine):
    return asyncio.run(coroutine)
