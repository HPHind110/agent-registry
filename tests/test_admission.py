import asyncio
import logging
import secrets

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_registry_client import RegistryClient
from registry.config import Settings
from registry.main import create_app
from test_registry import Clock, card


def test_admission_and_ownership_are_separate(card, tmp_path, caplog, monkeypatch):
    join = secrets.token_urlsafe()
    bad = secrets.token_urlsafe()
    db = tmp_path / 'registry.db'
    monkeypatch.setenv('REGISTRY_JOIN_TOKEN', join)
    monkeypatch.setenv('REGISTRY_ALLOW_OPEN_REGISTRATION', '1')  # configured token wins
    monkeypatch.setenv('REGISTRY_DATABASE_URL', 'sqlite:///' + db.as_posix())
    settings = Settings.from_env()
    assert join not in repr(settings)
    clock = Clock()
    caplog.set_level(logging.INFO)
    path = '/v1/agents/' + card['agent_id']
    with TestClient(create_app(settings, clock)) as web:
        for headers in ({}, {'X-Registry-Join-Token': bad}):
            response = web.post('/v1/agents', json=card, headers=headers)
            assert response.status_code == 403
            assert bad not in response.text
        assert web.get('/v1/agents?active_only=false').json() == []
        gate = {'X-Registry-Join-Token': join}
        first = web.post('/v1/agents', json=card, headers=gate)
        assert first.status_code == 201 and join not in first.text
        owner = first.json()['credential']
        auth = {'Authorization': 'Bearer ' + owner}
        for method, route, body in [('POST', '/v1/agents', card), ('POST', path+'/heartbeat', None),
                                    ('PATCH', path, {'name': 'changed'}), ('DELETE', path, None)]:
            assert web.request(method, route, headers=gate, json=body).status_code == 401
        clock.advance(10)
        beat = web.post(path+'/heartbeat', headers=auth).json()
        assert beat['lease_expires_at'] > first.json()['lease_expires_at']
        assert web.patch(path, json={'endpoint': 'https://provider.test/new'}, headers=auth).json()['endpoint'].endswith('/new')
        assert 'credential' not in beat
    monkeypatch.delenv('REGISTRY_JOIN_TOKEN')
    monkeypatch.delenv('REGISTRY_ALLOW_OPEN_REGISTRATION')
    with TestClient(create_app(Settings.from_env(), clock)) as restarted:
        assert restarted.post('/v1/agents', json=card | {'agent_id': 'new'}).status_code == 503
        renewed = restarted.post('/v1/agents', json=card, headers=auth)
        assert renewed.status_code == 200 and 'credential' not in renewed.json()
        assert restarted.post(path+'/unregister', headers=auth).json()['status'] == 'UNREGISTERED'
        assert owner not in restarted.get('/v1/agents?active_only=false').text
    for secret in (join, bad, owner):
        assert secret not in caplog.text
        assert secret.encode() not in db.read_bytes()


@pytest.mark.parametrize('configured', ['', '   '])
def test_blank_token_closes_new_registration(card, tmp_path, configured):
    settings = Settings(database_url='sqlite:///' + (tmp_path / 'new.db').as_posix(), join_token=configured)
    with TestClient(create_app(settings)) as web:
        assert web.post('/v1/agents', json=card).status_code == 503


def test_sdk_join_token_is_scoped_to_initial_registration(card, tmp_path):
    calls = []
    owner = secrets.token_urlsafe()
    join = secrets.token_urlsafe()

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(201, json=dict(credential=owner, heartbeat_interval_seconds=10, ttl_seconds=30))
        return httpx.Response(200, json=dict(heartbeat_interval_seconds=10, ttl_seconds=30))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            sdk = RegistryClient(card, 'https://registry.test', tmp_path / 'key', http, join_token=join)
            await sdk.register()
            await sdk.heartbeat()
            await sdk.register()
            await sdk.unregister()

    asyncio.run(run())
    assert calls[0].headers['X-Registry-Join-Token'] == join
    assert 'Authorization' not in calls[0].headers
    for request in calls[1:]:
        assert 'X-Registry-Join-Token' not in request.headers
        assert request.headers['Authorization'] == 'Bearer ' + owner
    for request in calls:
        assert join not in str(request.url) and join.encode() not in request.content
