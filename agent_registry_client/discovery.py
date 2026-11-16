"""Consumer-side discovery; no credentials or business requests sent to Registry."""
import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl, TypeAdapter, field_validator


class DiscoveryError(RuntimeError):
    pass


class Provider(BaseModel):
    model_config = ConfigDict(extra='ignore')
    agent_id: str
    endpoint: HttpUrl

    @field_validator('endpoint')
    @classmethod
    def safe_url(cls, value):
        if value.username is not None or value.password is not None or value.fragment is not None:
            raise ValueError('Endpoint must not contain credentials/fragment')
        return value


def discover(http, registry_url, capability, domain=None):
    params = {'capability': capability, 'active_only': 'true'}
    if domain is not None:
        params['domain'] = domain
    try:
        response = http.get(registry_url.rstrip('/') + '/v1/agents', params=params)
        response.raise_for_status()
        return TypeAdapter(list[Provider]).validate_python(response.json())
    except (httpx.HTTPError, ValueError):
        raise DiscoveryError('Registry discovery failed or returned invalid data') from None
