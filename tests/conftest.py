import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["SKAVA_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SKAVA_PUBLIC_BASE_URL"] = "http://testserver"
os.environ["SKAVA_ENV"] = "dev"
os.environ["INTERNAL_API_KEY"] = "test-internal-key"

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed import seed_data  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as db:
        seed_data(db)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.state.testing_session_local = testing_session_local
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
