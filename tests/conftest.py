"""Test fixtures: isolate each test run on a temp sqlite DB."""
import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    # Point the agent at a throwaway DB and force offline (sample) mode so tests
    # are deterministic and need no network/keys.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_PATH", path)
    monkeypatch.setenv("PREFER_SAMPLE_DATA", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("FRED_API_KEY", "")

    # Reset cached settings + engine so the new env is picked up.
    from app.utils import config
    from app.data import repository
    config.get_settings.cache_clear()
    repository._engine = None
    repository.init_db()
    yield
    try:
        os.remove(path)
    except OSError:
        pass
