from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from firefly_api.schemas.common import UtcDateTime

Role = Literal["viewer", "admin"]


class UsernameModel(BaseModel):
    username: str = Field(min_length=1, max_length=100)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value


class LoginRequest(UsernameModel):
    password: str = Field(min_length=1, max_length=128)


class UserCreate(UsernameModel):
    password: str = Field(min_length=8, max_length=128)
    role: Role
    enabled: bool = True


class UserUpdate(UsernameModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role
    enabled: bool = True


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    enabled: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime
    last_login_at: UtcDateTime | None


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    expiresIn: int = 900
    user: UserOut
