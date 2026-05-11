"""MQTT broker request/response schemas (§7.1, §12).

Passwords are accepted in request bodies (plain text per §12) but never
returned in response bodies.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime


class _BrokerBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    use_tls: bool = False
    client_id: str | None = Field(default=None, max_length=255)


class MqttBrokerCreate(_BrokerBase):
    password: str | None = Field(default=None, max_length=255)


class MqttBrokerUpdate(_BrokerBase):
    password: str | None = Field(default=None, max_length=255)


class MqttBrokerOut(_BrokerBase):
    id: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
