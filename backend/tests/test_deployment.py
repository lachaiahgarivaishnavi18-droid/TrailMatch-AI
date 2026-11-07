import importlib
import pytest
from app.db import database_url


@pytest.mark.parametrize("original,expected", [
    ("postgres://user:password@localhost/demo", "postgresql+psycopg://user:password@localhost/demo"),
    ("postgresql://user:password@localhost/demo", "postgresql+psycopg://user:password@localhost/demo"),
    ("sqlite:///./test.db", "sqlite:///./test.db"),
])
def test_database_url_normalization(monkeypatch, original, expected):
    monkeypatch.setenv("DATABASE_URL", original)
    assert database_url() == expected


def test_vercel_entrypoint_exposes_api_and_built_spa():
    module = importlib.import_module("backend.app.main")
    from fastapi.testclient import TestClient
    # Entrypoint import does not need a live production database at build time.
    client = TestClient(module.app)
    assert client.get("/api/health").status_code == 200
    if module.dist.exists():
        assert client.get("/").status_code == 200
        assert client.get("/matching").status_code == 200


def test_vercel_rejects_ephemeral_sqlite(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="durable PostgreSQL"):
        with TestClient(app):
            pass
