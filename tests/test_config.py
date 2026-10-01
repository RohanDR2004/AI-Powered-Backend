from app.config import Settings


def test_plain_postgresql_url_gets_asyncpg_driver():
    settings = Settings(database_url="postgresql://user:pass@host:5432/db")
    assert settings.database_url == "postgresql+asyncpg://user:pass@host:5432/db"


def test_asyncpg_url_is_left_unchanged():
    url = "postgresql+asyncpg://user:pass@host:5432/db"
    settings = Settings(database_url=url)
    assert settings.database_url == url


def test_sync_database_url_uses_psycopg2():
    settings = Settings(database_url="postgresql+asyncpg://user:pass@host:5432/db")
    assert settings.sync_database_url == "postgresql+psycopg2://user:pass@host:5432/db"
