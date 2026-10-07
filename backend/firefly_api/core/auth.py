from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from firefly_api.core.errors import FireflyError
from firefly_api.db.models import AuthSetting, User, UserSession, utc_now
from firefly_api.db.session import get_db
from firefly_api.schemas.users import TokenResponse, UserOut

logger = logging.getLogger(__name__)
hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
REFRESH_COOKIE = "firefly_refresh"
AUTH_PATH = "/api/v1/auth"
bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def unauthorized(description: str = "Authentication required.") -> FireflyError:
    return FireflyError(description, status_code=401, error_code="unauthorized")


def forbidden() -> FireflyError:
    return FireflyError("Administrator access required.", status_code=403, error_code="forbidden")


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except VerifyMismatchError:
        return False


def initialize_auth(db: Session) -> None:
    """Seed only an empty installation; keep the signing key across restarts."""
    db.execute(
        insert(AuthSetting)
        .values(id=1, signing_key=secrets.token_urlsafe(64))
        .on_conflict_do_nothing(index_elements=["id"])
    )
    if db.scalar(select(User.id).limit(1)) is None:
        db.add(User(username="admin", password_hash=hasher.hash("admin"), role="admin"))
        logger.warning("Created initial admin account. Change the default password promptly.")
    db.commit()


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def refresh_token(session_id: str) -> str:
    return f"{session_id}.{secrets.token_urlsafe(32)}"


def token_response(db: Session, user: User, session: UserSession) -> TokenResponse:
    setting = db.get(AuthSetting, 1)
    if setting is None:
        raise RuntimeError("Authentication is not initialized; run application bootstrap.")
    now = utc_now()
    token = jwt.encode(
        {
            "sub": str(user.id),
            "sid": session.id,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "iss": "firefly-api",
            "aud": "firefly-admin",
        },
        setting.signing_key,
        algorithm="HS256",
    )
    return TokenResponse(accessToken=token, user=UserOut.model_validate(user))


def current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise unauthorized()
    setting = db.get(AuthSetting, 1)
    if setting is None:
        raise RuntimeError("Authentication is not initialized; run application bootstrap.")
    try:
        claims = jwt.decode(
            credentials.credentials,
            setting.signing_key,
            algorithms=["HS256"],
            issuer="firefly-api",
            audience="firefly-admin",
            options={"require": ["sub", "sid", "iat", "exp"]},
        )
        user_id = int(claims["sub"])
        session_id = claims["sid"]
        if not isinstance(session_id, str):
            raise ValueError("Invalid session ID")
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise unauthorized("Invalid or expired access token.") from exc
    session = db.get(UserSession, session_id)
    user = db.get(User, user_id)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked
        or as_utc(session.expires_at) <= utc_now()
        or user is None
        or not user.enabled
    ):
        raise unauthorized("Session is no longer valid.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise forbidden()
    return user


def authorize_admin_api(request: Request, user: CurrentUser) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"} and user.role != "admin":
        raise forbidden()


def require_csrf_header(request: Request) -> None:
    # Cross-origin forms cannot send this header; no cross-origin CORS is enabled.
    if request.headers.get("X-Firefly-CSRF") != "1":
        raise FireflyError(
            "Missing CSRF protection header.", status_code=403, error_code="csrf_required"
        )


def revoke_user_sessions(db: Session, user_id: int) -> None:
    db.execute(update(UserSession).where(UserSession.user_id == user_id).values(revoked=True))
