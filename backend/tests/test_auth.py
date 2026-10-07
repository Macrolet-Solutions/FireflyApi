from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from firefly_api.api.admin.users import safe_to_remove_admin
from firefly_api.core.auth import REFRESH_COOKIE, hasher, initialize_auth
from firefly_api.core.startup import bootstrap
from firefly_api.db.models import AuthSetting, User, UserSession, utc_now
from firefly_api.db.session import create_engine_for_url, create_session_factory
from firefly_api.main import create_app

AUTH = "/api/v1/auth"
ADMIN = "/api/v1/admin"
CSRF = {"X-Firefly-CSRF": "1"}


def login(client, username="admin", password="admin"):
    response = client.post(
        f"{AUTH}/login",
        json={"username": username, "password": password},
        headers=CSRF,
    )
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['accessToken']}"
    return response


def create_user(client, username="reader", role="viewer", enabled=True):
    response = client.post(
        f"{ADMIN}/users",
        json={
            "username": username,
            "password": "test-password",
            "role": role,
            "enabled": enabled,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def anonymous(client):
    client.headers.pop("Authorization")
    client.cookies.clear()
    return client


def test_login_and_password_hash(anonymous, db):
    response = login(anonymous, " ADMIN ")
    data = response.json()
    assert set(data) == {"accessToken", "tokenType", "expiresIn", "user"}
    assert data["expiresIn"] == 900
    assert data["user"]["role"] == "admin"
    assert data["user"]["last_login_at"] is not None
    assert "password" not in str(data["user"])
    user = db.scalar(select(User).where(User.username == "admin"))
    assert user.password_hash != "admin"
    assert hasher.verify(user.password_hash, "admin")
    claims = jwt.decode(data["accessToken"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 900
    session = db.get(UserSession, claims["sid"])
    assert (session.expires_at - session.created_at).total_seconds() == 30 * 86400
    assert session.refresh_hash != anonymous.cookies.get(REFRESH_COOKIE)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/auth" in cookie
    assert 30 * 86400 - 5 <= int(cookie.split("Max-Age=")[1].split(";")[0]) <= 30 * 86400
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        "/mqtt-brokers",
        "/fireflies",
        "/led-states",
        "/command-presets",
        "/events",
        "/users",
    ],
)
def test_admin_reads_require_auth(anonymous, path):
    response = anonymous.get(ADMIN + path)
    assert response.status_code == 401
    assert response.json()["errorCode"] == "unauthorized"


def test_public_api_unchanged(anonymous):
    response = anonymous.get("/api/v1/public/fireflies/FF01/status")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "runtime_not_started"
    for endpoint in ["slots:update", "slots:update-all", "load-slots"]:
        response = anonymous.post(
            f"/api/v1/public/fireflies/FF01/{endpoint}",
            json={},
        )
        assert response.status_code == 503
        assert response.json()["errorCode"] == "runtime_not_started"


def test_viewer_reads_and_credentials_redacted(client, broker):
    create_user(client)
    login(client, "reader", "test-password")
    for path in ["/mqtt-brokers", "/fireflies", "/led-states", "/command-presets", "/events"]:
        assert client.get(ADMIN + path).status_code == 200
    data = client.get(f"{ADMIN}/mqtt-brokers/{broker['id']}").json()
    assert data["host"] == "localhost" and data["username"] == "user"
    assert "password" not in data
    assert client.get(f"{ADMIN}/users").status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/mqtt-brokers"),
        ("PUT", "/mqtt-brokers/1"),
        ("DELETE", "/mqtt-brokers/1"),
        ("POST", "/mqtt-brokers/1:test-connection"),
        ("POST", "/fireflies"),
        ("PUT", "/fireflies/1"),
        ("DELETE", "/fireflies/1"),
        ("POST", "/fireflies/1/segments"),
        ("PUT", "/fireflies/1/segments/1"),
        ("DELETE", "/fireflies/1/segments/1"),
        ("POST", "/fireflies/1/segments/copy-from/2"),
        ("POST", "/fireflies/1/slots"),
        ("PUT", "/fireflies/1/slots/1"),
        ("DELETE", "/fireflies/1/slots/1"),
        ("PUT", "/fireflies/1/slots:replace"),
        ("POST", "/fireflies/1:start-actor"),
        ("POST", "/fireflies/1:stop-actor"),
        ("POST", "/fireflies/1:reinitialize"),
        ("POST", "/fireflies/1:reset"),
        ("POST", "/fireflies/1/slots:test"),
        ("POST", "/led-states"),
        ("PUT", "/led-states/1"),
        ("DELETE", "/led-states/1"),
        ("POST", "/command-presets"),
        ("PUT", "/command-presets/1"),
        ("DELETE", "/command-presets/1"),
        ("POST", "/users"),
        ("PUT", "/users/1"),
        ("DELETE", "/users/1"),
    ],
)
def test_viewer_cannot_mutate_any_admin_surface(client, method, path):
    create_user(client)
    login(client, "reader", "test-password")
    assert client.request(method, ADMIN + path, json={}).status_code == 403


def test_refresh_rotates_and_replay_revokes(anonymous):
    first = login(anonymous)
    old_cookie = anonymous.cookies.get(REFRESH_COOKIE)
    refreshed = anonymous.post(f"{AUTH}/refresh", headers=CSRF)
    assert refreshed.status_code == 200
    assert anonymous.cookies.get(REFRESH_COOKIE) != old_cookie
    anonymous.headers["Authorization"] = f"Bearer {refreshed.json()['accessToken']}"
    assert anonymous.get(f"{AUTH}/me").status_code == 200
    replay = anonymous.post(
        f"{AUTH}/refresh",
        headers={**CSRF, "Cookie": f"{REFRESH_COOKIE}={old_cookie}"},
    )
    assert replay.status_code == 401
    assert anonymous.get(f"{AUTH}/me").status_code == 401
    anonymous.headers["Authorization"] = f"Bearer {first.json()['accessToken']}"
    assert anonymous.get(f"{AUTH}/me").status_code == 401


def test_refresh_survives_app_restart(client, app_config, session_factory):
    app = create_app(app_config)
    app.state.session_factory = session_factory
    with TestClient(app) as other:
        other.cookies.update(client.cookies)
        response = other.post(f"{AUTH}/refresh", headers=CSRF)
        assert response.status_code == 200
        other.headers["Authorization"] = f"Bearer {response.json()['accessToken']}"
        assert other.get(f"{AUTH}/me").status_code == 200


def test_logout_revokes_access_and_refresh(client):
    assert client.post(f"{AUTH}/logout", headers=CSRF).status_code == 204
    assert client.get(f"{AUTH}/me").status_code == 401
    assert client.post(f"{AUTH}/refresh", headers=CSRF).status_code == 401
    assert client.cookies.get(REFRESH_COOKIE) is None


@pytest.mark.parametrize("path", ["/login", "/refresh", "/logout"])
def test_cookie_endpoints_require_csrf(client, path):
    response = client.post(AUTH + path, json={"username": "admin", "password": "admin"})
    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_required"


@pytest.mark.parametrize("kind", ["expired", "bad_signature", "none_algorithm", "bad_subject"])
def test_invalid_access_tokens_rejected(client, db, kind):
    key = db.get(AuthSetting, 1).signing_key
    claims = jwt.decode(client.headers["Authorization"][7:], options={"verify_signature": False})
    if kind == "expired":
        claims["exp"] = utc_now() - timedelta(seconds=1)
    if kind == "bad_subject":
        claims["sub"] = "not-an-id"
    token = jwt.encode(
        claims,
        None if kind == "none_algorithm" else "x" * 64 if kind == "bad_signature" else key,
        algorithm="none" if kind == "none_algorithm" else "HS256",
    )
    assert client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_session_absolute_expiry(client, db):
    claims = jwt.decode(client.headers["Authorization"][7:], options={"verify_signature": False})
    session = db.get(UserSession, claims["sid"])
    session.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    assert client.get(f"{AUTH}/me").status_code == 401
    assert client.post(f"{AUTH}/refresh", headers=CSRF).status_code == 401


def test_user_uniqueness_validation_and_no_hash_exposure(client):
    created = create_user(client, " MixedCase ")
    assert created["username"] == "mixedcase"
    assert "password_hash" not in created
    duplicate = client.post(
        f"{ADMIN}/users",
        json={
            "username": "MIXEDCASE",
            "password": "test-password",
            "role": "admin",
        },
    )
    assert duplicate.status_code == 409
    for values in [
        {"username": " ", "password": "test-password", "role": "admin"},
        {"username": "new", "password": "short", "role": "admin"},
        {"username": "new", "password": "test-password", "role": "invalid"},
    ]:
        assert client.post(f"{ADMIN}/users", json=values).status_code == 422
    assert client.get(f"{ADMIN}/users").status_code == 200
    assert (
        client.put(
            f"{ADMIN}/users/999",
            json={
                "username": "missing",
                "role": "viewer",
                "enabled": True,
            },
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "change",
    [
        {"role": "admin"},
        {"enabled": False},
        {"password": "new-password"},
        {"username": "renamed"},
    ],
)
def test_user_changes_revoke_sessions(client, app_config, session_factory, change):
    reader = create_user(client)
    app = create_app(app_config)
    app.state.session_factory = session_factory
    with TestClient(app) as other:
        login(other, "reader", "test-password")
        response = client.put(
            f"{ADMIN}/users/{reader['id']}",
            json={
                "username": "reader",
                "role": "viewer",
                "enabled": True,
                **change,
            },
        )
        assert response.status_code == 200, response.text
        assert other.get(f"{AUTH}/me").status_code == 401
        assert other.post(f"{AUTH}/refresh", headers=CSRF).status_code == 401


def test_delete_user_cascades_sessions(client, db):
    reader = create_user(client)
    reader_token = login(client, "reader", "test-password").json()["accessToken"]
    login(client)
    assert client.delete(f"{ADMIN}/users/{reader['id']}").status_code == 204
    assert (
        db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(
                UserSession.user_id == reader["id"],
            )
        )
        == 0
    )
    assert (
        client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {reader_token}"}).status_code
        == 401
    )


def test_last_enabled_admin_guard(client):
    admin_id = client.get(f"{AUTH}/me").json()["id"]
    create_user(client, "disabled-admin", "admin", enabled=False)
    assert client.delete(f"{ADMIN}/users/{admin_id}").status_code == 409
    for change in [{"role": "viewer"}, {"enabled": False}]:
        assert (
            client.put(
                f"{ADMIN}/users/{admin_id}",
                json={
                    "username": "admin",
                    "role": "admin",
                    "enabled": True,
                    **change,
                },
            ).status_code
            == 409
        )
    second = create_user(client, "second-admin", "admin")
    assert client.delete(f"{ADMIN}/users/{second['id']}").status_code == 204
    assert client.get(f"{AUTH}/me").status_code == 200


def test_admin_can_be_demoted_if_another_enabled_admin_exists(client):
    create_user(client, "second-admin", "admin")
    admin_id = client.get(f"{AUTH}/me").json()["id"]
    response = client.put(
        f"{ADMIN}/users/{admin_id}",
        json={
            "username": "admin",
            "role": "viewer",
            "enabled": True,
        },
    )
    assert response.status_code == 200
    assert client.get(f"{AUTH}/me").status_code == 401


def test_self_password_change_revokes_all_sessions_and_preserves_admin(
    client, app_config, session_factory
):
    app = create_app(app_config)
    app.state.session_factory = session_factory
    with TestClient(app) as other:
        login(other)
        assert (
            client.post(
                f"{AUTH}/password",
                json={
                    "current_password": "wrong",
                    "new_password": "new-password",
                },
            ).status_code
            == 401
        )
        assert client.get(f"{AUTH}/me").status_code == 200
        assert (
            client.post(
                f"{AUTH}/password",
                json={
                    "current_password": "admin",
                    "new_password": "new-password",
                },
            ).status_code
            == 204
        )
        assert client.get(f"{AUTH}/me").status_code == 401
        assert other.get(f"{AUTH}/me").status_code == 401
        login(client, password="new-password")


def test_viewer_can_change_own_password(client):
    create_user(client)
    login(client, "reader", "test-password")
    assert (
        client.post(
            f"{AUTH}/password",
            json={
                "current_password": "test-password",
                "new_password": "changed-password",
            },
        ).status_code
        == 204
    )
    login(client, "reader", "changed-password")


def test_login_lockout_and_disabled_account(client):
    create_user(client)
    create_user(client, "disabled", enabled=False)
    for _ in range(5):
        assert (
            client.post(
                f"{AUTH}/login",
                headers=CSRF,
                json={
                    "username": "reader",
                    "password": "wrong",
                },
            ).status_code
            == 401
        )
    for username in ["reader", "disabled", "unknown"]:
        assert (
            client.post(
                f"{AUTH}/login",
                headers=CSRF,
                json={
                    "username": username,
                    "password": "test-password",
                },
            ).status_code
            == 401
        )


def test_secure_cookie_configuration(client, app_config):
    app_config.auth.cookie_secure = True
    response = login(client)
    assert "Secure" in response.headers["set-cookie"]


def test_migration_and_bootstrap_do_not_reset_accounts(app_config, tmp_path):
    app_config.database.url = f"sqlite:///{tmp_path / 'auth.db'}"
    bootstrap(app_config)
    engine = create_engine_for_url(app_config.database.url)
    factory = create_session_factory(engine)
    try:
        with factory() as db:
            admin = db.scalar(select(User))
            assert admin.username == "admin"
            admin.password_hash = hasher.hash("changed-password")
            admin.username = "owner"
            db.commit()
            key = db.get(AuthSetting, 1).signing_key
        bootstrap(app_config)
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 1
            admin = db.scalar(select(User))
            assert admin.username == "owner"
            assert hasher.verify(admin.password_hash, "changed-password")
            assert db.get(AuthSetting, 1).signing_key == key
            initialize_auth(db)
            assert db.scalar(select(func.count()).select_from(User)) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("operation", ["delete", "demote", "disable"])
def test_concurrent_last_admin_guard(app_config, tmp_path, operation):
    app_config.database.url = f"sqlite:///{tmp_path / 'concurrent.db'}"
    bootstrap(app_config)
    engine = create_engine_for_url(app_config.database.url)
    factory = create_session_factory(engine)
    barrier = Barrier(2)
    try:
        with factory() as db:
            db.add(
                User(username="second", password_hash=hasher.hash("test-password"), role="admin")
            )
            db.commit()
            ids = list(db.scalars(select(User.id)))

        def remove_admin(user_id):
            with factory() as db:
                if operation == "delete":
                    statement = delete(User)
                else:
                    statement = update(User).values(
                        role="viewer" if operation == "demote" else "admin",
                        enabled=operation != "disable",
                    )
                barrier.wait(timeout=5)
                result = db.execute(statement.where(User.id == user_id, safe_to_remove_admin()))
                db.commit()
                return result.rowcount

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(remove_admin, ids)) == [0, 1]
        with factory() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(
                        User.role == "admin",
                        User.enabled.is_(True),
                    )
                )
                == 1
            )
    finally:
        engine.dispose()
