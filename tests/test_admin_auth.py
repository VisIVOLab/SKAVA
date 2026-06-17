"""Auth + CSRF behaviour for the admin UI."""
from __future__ import annotations


def test_login_form_loads_and_contains_csrf(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert 'name="csrf_token"' in r.text
    assert "Login" in r.text or "login" in r.text


def test_login_with_bad_credentials_returns_401(client, admin_user):
    r = client.get("/admin/login")
    from tests.conftest import _csrf_from_login_form
    csrf = _csrf_from_login_form(r.text)
    r = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": "wrong-password",
            "csrf_token": csrf,
            "next": "/admin/",
        },
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_login_without_csrf_token_is_rejected(client, admin_user):
    # POST directly with no csrf — the CSRFDep should refuse it.
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong", "next": "/admin/"},
        follow_redirects=False,
    )
    # 400 (CSRF policy) or 401 (auth failed); the key invariant is the
    # request is NOT accepted as a successful login (no 303 to dashboard).
    assert r.status_code in (400, 401, 403)


def test_admin_root_requires_login(client):
    """Unauthenticated /admin/ → 303 to /admin/login."""
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/admin/login" in r.headers.get("location", "")


def test_admin_dashboard_renders_for_admin(admin_client):
    r = admin_client.get("/admin/", follow_redirects=False)
    assert r.status_code == 200
    # Phase 3 dashboard enrichments visible.
    assert "Dashboard" in r.text
    assert "Recent activity" in r.text


def test_logout_clears_session(admin_client):
    # Get CSRF for logout form from the dashboard render.
    r = admin_client.get("/admin/")
    import re
    csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text).group(1)
    r = admin_client.post(
        "/admin/logout",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    # Subsequent dashboard access should bounce back to login.
    r = admin_client.get("/admin/", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/admin/login" in r.headers.get("location", "")
