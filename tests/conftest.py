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


# ── Admin UI fixtures (Phase 4) ──────────────────────────────────────────────


_ADMIN_PASSWORD = "AdminPassword1!"  # meets default policy (12+ chars, mixed)


@pytest.fixture()
def admin_user(client):
    """Create (idempotent) an ``admin``-role user in the test DB.

    Uses the same ``testing_session_local`` set up by :func:`client` so
    the user is visible to subsequent admin requests. Returns the User
    instance for tests that need to assert against its id/role.
    """
    from app.admin.auth.password import hash_password
    from app.models.user import User, UserRole

    sess_factory = app.state.testing_session_local
    with sess_factory() as db:
        existing = db.query(User).filter(User.username == "admin").one_or_none()
        if existing:
            return existing
        u = User(
            username="admin",
            email="admin@example.org",
            full_name="Test Admin",
            role=UserRole.admin.value,
            password_hash=hash_password(_ADMIN_PASSWORD),
            is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u


def _csrf_from_login_form(html: str) -> str:
    """Extract the ``csrf_token`` hidden input value from a login form HTML.

    Cheap regex parse — no need for BeautifulSoup in the test path.
    Raises on miss so tests fail fast if the form template changes.
    """
    import re
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        raise AssertionError("csrf_token hidden input not found in login form")
    return m.group(1)


@pytest.fixture()
def admin_client(client, admin_user):
    """A :class:`TestClient` already logged in as the admin user.

    Performs a real GET /admin/login (to capture the CSRF token + set
    the session cookie) followed by POST /admin/login. Subsequent
    requests reuse the cookie jar automatically.
    """
    r = client.get("/admin/login")
    assert r.status_code == 200, r.text
    csrf = _csrf_from_login_form(r.text)
    r = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": _ADMIN_PASSWORD,
            "csrf_token": csrf,
            "next": "/admin/",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), (
        f"Login failed: status={r.status_code}, body={r.text[:200]}"
    )
    return client
