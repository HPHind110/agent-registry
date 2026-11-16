"""Common demo protocol v1; the caller supplies the business response schema."""
import httpx
from pydantic import BaseModel, ConfigDict


class InvocationError(RuntimeError):
    pass


class Envelope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    agent_id: str
    capability: str
    output: dict


def invoke_first(http, providers, capability, data, output_schema):
    if not providers:
        raise InvocationError('No ONLINE provider for requested capability')
    for provider in providers:
        try:
            response = http.post(str(provider.endpoint), json={'capability': capability, 'input': data})
            response.raise_for_status()
            body = Envelope.model_validate(response.json())
            if body.agent_id != provider.agent_id or body.capability != capability:
                raise ValueError('Provider response identity/capability mismatch')
            output = output_schema.model_validate(body.output)
            return output.model_dump(mode='json'), provider.agent_id
        except (httpx.HTTPError, ValueError):
            continue
    raise InvocationError('All providers failed HTTP, connection or response validation')
