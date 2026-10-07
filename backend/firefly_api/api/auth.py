import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import case, delete, select, update

from firefly_api.core.auth import (
    AUTH_PATH,
    DUMMY_HASH,
    REFRESH_COOKIE,
    CurrentUser,
    DbSession,
    as_utc,
    hash_refresh,
    hasher,
    refresh_token,
    require_csrf_header,
    revoke_user_sessions,
    token_response,
    unauthorized,
    verify_password,
)
from firefly_api.db.models import User, UserSession, utc_now
from firefly_api.schemas.users import LoginRequest, PasswordChange, TokenResponse, UserOut

router = APIRouter(prefix=AUTH_PATH, tags=["authentication"])


def set_refresh_cookie(
    request: Request,
    response: Response,
    token: str,
    session: UserSession,
) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=max(0, int((as_utc(session.expires_at) - utc_now()).total_seconds())),
        httponly=True,
        secure=request.app.state.config.auth.cookie_secure,
        samesite="strict",
        path=AUTH_PATH,
    )
    response.headers["Cache-Control"] = "no-store"


def clear_refresh_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=AUTH_PATH,
        secure=request.app.state.config.auth.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(require_csrf_header)])
def login(data: LoginRequest, db: DbSession, request: Request, response: Response) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == data.username))
    now = utc_now()
    valid = verify_password(user.password_hash if user else DUMMY_HASH, data.password)
    if (
        user is None
        or not user.enabled
        or not valid
        or (user.locked_until is not None and as_utc(user.locked_until) > now)
    ):
        if user is not None and (user.locked_until is None or as_utc(user.locked_until) <= now):
            db.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    failed_login_attempts=case(
                        (User.failed_login_attempts >= 4, 0),
                        else_=User.failed_login_attempts + 1,
                    ),
                    locked_until=case(
                        (User.failed_login_attempts >= 4, now + timedelta(minutes=15)),
                        else_=User.locked_until,
                    ),
                )
            )
            db.commit()
        raise unauthorized("Invalid credentials or account temporarily locked.")
    updated = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.enabled.is_(True),
            User.username == data.username,
            User.password_hash == user.password_hash,
            (User.locked_until.is_(None) | (User.locked_until <= now)),
        )
        .values(
            failed_login_attempts=0,
            locked_until=None,
            last_login_at=now,
            password_hash=hasher.hash(data.password)
            if hasher.check_needs_rehash(user.password_hash)
            else user.password_hash,
        )
    )
    if updated.rowcount != 1:
        db.rollback()
        raise unauthorized("Account changed during login. Please try again.")
    db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    session_id = secrets.token_urlsafe(32)
    token = refresh_token(session_id)
    session = UserSession(
        id=session_id,
        user_id=user.id,
        refresh_hash=hash_refresh(token),
        created_at=now,
        expires_at=now + timedelta(days=30),
    )
    db.add(session)
    db.commit()
    db.refresh(user)
    set_refresh_cookie(request, response, token, session)
    return token_response(db, user, session)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(require_csrf_header)])
def refresh(db: DbSession, request: Request, response: Response) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE, "")
    session_id, separator, _secret = token.partition(".")
    if not separator or not token.isascii() or len(token) > 200:
        raise unauthorized("Invalid refresh token.")
    session = db.get(UserSession, session_id)
    if session is None or session.revoked or as_utc(session.expires_at) <= utc_now():
        raise unauthorized("Session expired. Please sign in again.")
    user = db.get(User, session.user_id)
    if user is None or not user.enabled:
        raise unauthorized("Session is no longer valid.")
    replacement = refresh_token(session.id)
    rotated = db.execute(
        update(UserSession)
        .where(
            UserSession.id == session.id,
            UserSession.refresh_hash == hash_refresh(token),
            UserSession.revoked.is_(False),
            UserSession.expires_at > utc_now(),
        )
        .values(refresh_hash=hash_refresh(replacement)),
        execution_options={"synchronize_session": False},
    )
    if rotated.rowcount != 1:
        db.execute(update(UserSession).where(UserSession.id == session.id).values(revoked=True))
        db.commit()
        raise unauthorized("Refresh token was reused. Please sign in again.")
    db.commit()
    set_refresh_cookie(request, response, replacement, session)
    return token_response(db, user, session)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf_header)])
def logout(db: DbSession, request: Request, response: Response) -> None:
    token = request.cookies.get(REFRESH_COOKIE, "")
    session_id, separator, _secret = token.partition(".")
    if separator and token.isascii() and len(token) <= 200:
        db.execute(
            update(UserSession)
            .where(
                UserSession.id == session_id,
                UserSession.refresh_hash == hash_refresh(token),
            )
            .values(revoked=True)
        )
        db.commit()
    clear_refresh_cookie(request, response)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser, response: Response) -> User:
    response.headers["Cache-Control"] = "no-store"
    return user


@router.post("/password", status_code=204)
def change_password(
    data: PasswordChange,
    user: CurrentUser,
    db: DbSession,
    request: Request,
    response: Response,
) -> None:
    if not verify_password(user.password_hash, data.current_password):
        raise unauthorized("Current password is incorrect.")
    user.password_hash = hasher.hash(data.new_password)
    revoke_user_sessions(db, user.id)
    db.commit()
    clear_refresh_cookie(request, response)
