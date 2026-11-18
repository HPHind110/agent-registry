"""Common demo protocol v1; the caller supplies the business response schema."""
from functools import partial

import httpx
from pydantic import BaseModel, ConfigDict

from .discovery import DiscoveryError, discover


class InvocationError(RuntimeError):
    pass


class _FailedRound(InvocationError):
    """All candidates failed. Only sanitized failure categories leave this module."""

    def __init__(self, reasons, input_rejected):
        super().__init__('All providers failed: ' + ', '.join(sorted(reasons)))
        self.input_rejected = input_rejected


class Envelope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    agent_id: str
    capability: str
    output: dict


def invoke_first(http, providers, capability, data, output_schema):
    return _invoke_round(http.post, providers, capability, data, output_schema)


def _invoke_round(post, providers, capability, data, output_schema):
    if not providers:
        raise InvocationError('No ONLINE provider for requested capability')
    reasons = set()
    input_rejected = False
    for provider in providers:
        try:
            response = post(str(provider.endpoint), json={'capability': capability, 'input': data})
            response.raise_for_status()
            body = Envelope.model_validate(response.json())
            if body.agent_id != provider.agent_id or body.capability != capability:
                raise ValueError('Provider response identity/capability mismatch')
            output = output_schema.model_validate(body.output)
            return output.model_dump(mode='json'), provider.agent_id
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            reasons.add(f'HTTP {status}')
            if status in (400, 422):
                input_rejected = True
        except httpx.HTTPError:
            reasons.add('HTTP transport error')
        except ValueError:
            reasons.add('invalid provider response')
    raise _FailedRound(reasons, input_rejected)


def _new_bindings(providers, seen):
    candidates = []
    for provider in providers:
        binding = (provider.agent_id, str(provider.endpoint))
        if binding not in seen:
            seen.add(binding)
            candidates.append(provider)
    return candidates


def _without_registry_auth(request):
    # Override client-level HTTPX auth and remove any default Bearer header.
    request.headers.pop('Authorization', None)
    return request


def invoke_with_rediscovery(http, registry_url, capability, data, output_schema,
                            domain=None, *, safe_to_retry=False):
    """Discover and invoke; opt in to one fresh list of untried bindings for safe operations."""
    seen = set()
    providers = discover(http, registry_url, capability, domain)
    post = partial(http.post, auth=_without_registry_auth)
    try:
        return _invoke_round(post, _new_bindings(providers, seen), capability, data, output_schema)
    except _FailedRound as first:
        if not safe_to_retry or first.input_rejected:
            raise
        first_failure = str(first)

    try:
        refreshed = discover(http, registry_url, capability, domain)
    except DiscoveryError as exc:
        raise DiscoveryError(f'Rediscovery failed after initial invocation ({first_failure}): {exc}') from exc

    candidates = _new_bindings(refreshed, seen)
    if not candidates:
        raise InvocationError(f'Rediscovery found no new provider binding ({first_failure})')
    try:
        return _invoke_round(post, candidates, capability, data, output_schema)
    except _FailedRound as exc:
        raise InvocationError(f'Invocation after rediscovery failed: {exc}. Initial invocation: {first_failure}') from exc
