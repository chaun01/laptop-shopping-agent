import shutil

import pytest

from laptop_agent.config import get_settings


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Copy shop.db so tests that write (cart, orders) never touch the real database.
    DB_PATH is also inherited by the MCP server subprocess."""
    src = get_settings().db_path
    dst = tmp_path / "shop.db"
    shutil.copy(src, dst)
    monkeypatch.setenv("DB_PATH", str(dst))
    get_settings.cache_clear()
    yield dst
    get_settings.cache_clear()
