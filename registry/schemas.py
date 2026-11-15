import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from .leases import Status


def normalize(value: str) -> str:
    result = re.sub(r'[\s-]+', '_', value.strip().lower())
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.:]{0,99}', result):
        raise ValueError('Use 1-100 ASCII letters, digits, spaces, hyphens, _, . or :')
    return result


class CardFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=1000)
    capabilities: list[str] = Field(min_length=1, max_length=100)
    endpoint: HttpUrl = Field(max_length=2048)
    version: str = Field(min_length=1, max_length=64)

    @field_validator('domain')
    @classmethod
    def domain_normalized(cls, value):
        return normalize(value)

    @field_validator('capabilities')
    @classmethod
    def capabilities_normalized(cls, value):
        return sorted(set(normalize(item) for item in value))

    @field_validator('endpoint')
    @classmethod
    def endpoint_without_credentials(cls, value):
        if value.username is not None or value.password is not None or value.fragment is not None:
            raise ValueError('Endpoint cannot contain credentials or fragment')
        return value


class AgentCard(CardFields):
    agent_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


class AgentPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = None
    domain: str | None = None
    description: str | None = None
    capabilities: list[str] | None = None
    endpoint: str | None = None
    version: str | None = None

    @model_validator(mode='after')
    def validate_fields(self):
        values = self.model_dump(exclude_unset=True)
        if not values or any(value is None for value in values.values()):
            raise ValueError('PATCH must contain at least one non-null card field')
        defaults = dict(name='x', domain='x', description='', capabilities=['x'],
                        endpoint='http://localhost/', version='1')
        CardFields.model_validate(defaults | values)
        return self


class AgentView(AgentCard):
    registered_at: datetime
    updated_at: datetime
    last_heartbeat: datetime
    lease_expires_at: datetime
    status: Status


class Registration(AgentView):
    credential: str | None = None
    heartbeat_interval_seconds: int
    ttl_seconds: int


class AgentStatus(BaseModel):
    agent_id: str
    status: Status
    last_heartbeat: datetime
    lease_expires_at: datetime


class Health(BaseModel):
    status: Literal['ok']
    server_time: datetime
    heartbeat_interval_seconds: int
    ttl_seconds: int
