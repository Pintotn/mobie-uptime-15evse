from mobie_uptime.db import _normalise_database_url


def test_render_postgres_url_uses_psycopg3() -> None:
    assert (
        _normalise_database_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg://user:pass@host:5432/db"
    )


def test_sqlite_url_is_unchanged() -> None:
    assert _normalise_database_url("sqlite:///./data/test.db") == "sqlite:///./data/test.db"
