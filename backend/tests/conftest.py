import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["LLM_PROVIDER"] = "none"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db import Base, get_session
from app.main import app
from app.seed import seed


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        seed(session)
    def override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_session] = override
    # Avoid application seed of global DB; fixture seeds the isolated dependency instead.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
