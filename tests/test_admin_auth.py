# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
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


def _try_login(client, password):
    from tests.conftest import _csrf_from_login_form
    csrf = _csrf_from_login_form(client.get("/admin/login").text)
    return client.post("/admin/login", data={
        "username": "admin", "password": password, "csrf_token": csrf, "next": "/admin/",
    }, follow_redirects=False)


def test_repeated_failed_logins_are_throttled(client, admin_user, monkeypatch):
    from app.admin.config import admin_settings
    from tests.conftest import _ADMIN_PASSWORD
    monkeypatch.setattr(admin_settings, "login_rate_limit_per_minute", 3)
    for _ in range(3):
        assert _try_login(client, "wrong-password").status_code == 401
    # Over the limit: refused before the password is checked, even the right one.
    r = _try_login(client, _ADMIN_PASSWORD)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert "Too many failed sign-ins" in r.text


def test_a_successful_login_clears_the_count(client, admin_user, monkeypatch):
    from app.admin.config import admin_settings
    from tests.conftest import _ADMIN_PASSWORD
    monkeypatch.setattr(admin_settings, "login_rate_limit_per_minute", 3)
    for _ in range(2):
        _try_login(client, "wrong-password")
    assert _try_login(client, _ADMIN_PASSWORD).status_code in (302, 303)
    client.post("/admin/logout", follow_redirects=False)
    for _ in range(2):
        assert _try_login(client, "wrong-password").status_code == 401


def test_the_throttle_window_slides():
    from app.admin.auth import throttle
    for t in (0.0, 1.0, 2.0):
        throttle.record_failure("10.0.0.1", now=t)
    assert throttle.retry_after("10.0.0.1", 3, now=30.0) == 31
    assert throttle.retry_after("10.0.0.1", 3, now=60.5) == 0      # the first left the window
    assert throttle.retry_after("10.0.0.1", 0, now=1.0) == 0       # 0 disables it
    assert throttle.retry_after("10.0.0.2", 3, now=1.0) == 0       # per client


def test_clients_that_never_return_are_forgotten():
    from app.admin.auth import throttle
    for i in range(1000):
        throttle.record_failure(f"client-{i}", now=0.0)
    throttle.retry_after("someone-else", 6, now=120.0)
    assert len(throttle._failures) == 0
