from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from firefly_api.core.auth import DbSession, hasher, require_admin, revoke_user_sessions
from firefly_api.core.errors import ConflictError, NotFoundError
from firefly_api.db.models import User
from firefly_api.schemas.users import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["admin:users"], dependencies=[Depends(require_admin)])


def get_user(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.", error_code="user_not_found")
    return user


def commit_user(db: DbSession) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Username already exists.", error_code="username_exists") from exc


def safe_to_remove_admin() -> ColumnElement[bool]:
    # The guard is evaluated inside the write, preventing concurrent last-admin removals.
    admin_count = (
        select(func.count(User.id))
        .where(
            User.role == "admin",
            User.enabled.is_(True),
        )
        .scalar_subquery()
    )
    return or_(User.role != "admin", User.enabled.is_(False), admin_count > 1)


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: DbSession) -> User:
    user = User(
        username=data.username,
        password_hash=hasher.hash(data.password),
        role=data.role,
        enabled=data.enabled,
    )
    db.add(user)
    commit_user(db)
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: DbSession) -> User:
    user = get_user(db, user_id)
    revoke = (
        data.password is not None
        or user.role != data.role
        or user.enabled != data.enabled
        or user.username != data.username
    )
    values = data.model_dump(exclude={"password"})
    if data.password is not None:
        values["password_hash"] = hasher.hash(data.password)
        values["failed_login_attempts"] = 0
        values["locked_until"] = None
    statement = update(User).where(User.id == user_id)
    if data.role != "admin" or not data.enabled:
        statement = statement.where(safe_to_remove_admin())
    try:
        result = db.execute(statement.values(**values))
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Username already exists.", error_code="username_exists") from exc
    if result.rowcount != 1:
        db.rollback()
        raise ConflictError("The last enabled admin cannot be demoted or disabled.")
    if revoke:
        revoke_user_sessions(db, user_id)
    commit_user(db)
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: DbSession) -> None:
    get_user(db, user_id)
    result = db.execute(delete(User).where(User.id == user_id, safe_to_remove_admin()))
    if result.rowcount != 1:
        db.rollback()
        raise ConflictError("The last enabled admin cannot be deleted.")
    db.commit()
