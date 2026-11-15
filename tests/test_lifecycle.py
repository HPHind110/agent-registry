import asyncio
import sqlite3

import httpx
import pytest

from demo.registry_client import RegistryClient
from registry.database import create_database
from test_registry import env, card, register


def test_suspect_boundary_and_recovery(env, card):
    client, clock, _ = env
    _, headers = register(client, card)
    clock.advance(11)  # One missed interval does not immediately imply failure.
    assert client.get('/v1/agents/weather-1/status').json()['status'] == 'ONLINE'
    clock.advance(9)
    assert client.get('/v1/agents/weather-1/status').json()['status'] == 'SUSPECT'
    assert client.get('/v1/agents').json() == []
    assert len(client.get('/v1/agents?active_only=false').json()) == 1
    assert client.post('/v1/agents/weather-1/heartbeat', headers=headers).json()['status'] == 'ONLINE'


def test_repeated_heartbeat_survives_many_leases(env, card):
    client, clock, _ = env
    original, headers = register(client, card)
    for _ in range(20):
        clock.advance(10)
        body = client.post('/v1/agents/weather-1/heartbeat', headers=headers).json()
        assert body['status'] == 'ONLINE'
        assert len(client.get('/v1/agents').json()) == 1
    assert body['last_heartbeat'] != original['last_heartbeat']


def test_withdraw_preserves_ownership_and_restart_binding(env, card):
    client, _, _ = env
    original, headers = register(client, card)
    path = '/v1/agents/weather-1'
    assert client.post(path + '/unregister').status_code == 401
    assert client.post(path + '/unregister', headers=headers).json()['status'] == 'UNREGISTERED'
    assert client.get('/v1/agents').json() == []
    assert client.post(path + '/heartbeat', headers=headers).status_code == 409
    assert client.post('/v1/agents', json=card).status_code == 401
    new = client.post('/v1/agents', json=card | {'endpoint': 'http://localhost:9005/forecast'}, headers=headers).json()
    assert new['registered_at'] == original['registered_at']
    assert new['status'] == 'ONLINE'
    assert client.get('/v1/agents').json()[0]['endpoint'] == 'http://localhost:9005/forecast'


def test_additive_database_migration(tmp_path):
    path = tmp_path / 'old.db'
    url = 'sqlite:///' + path.as_posix()
    engine, _ = create_database(url)
    engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE agents DROP COLUMN withdrawn')
    engine, _ = create_database(url)
    engine.dispose()
    with sqlite3.connect(path) as db:
        assert 'withdrawn' in [row[1] for row in db.execute('PRAGMA table_info(agents)')]


def test_agent_background_retry_renew_recover_and_unregister(env, card, tmp_path):
    client, clock, _ = env

    async def scenario():
        calls, sleeps = [], []
        def handler(request):
            calls.append(request.url.path)
            if len(calls) == 1:
                raise httpx.ConnectError('offline', request=request)
            response = client.request(request.method, request.url.path,
                                      content=request.content, headers=dict(request.headers))
            return httpx.Response(response.status_code, content=response.content)
        lifecycle = None
        async def sleep(delay):
            sleeps.append(delay)
            if len(sleeps) == 3:
                clock.advance(31)  # Outage outlasts lease; heartbeat gets 409.
            else:
                clock.advance(delay)
            if len(sleeps) == 5:
                raise asyncio.CancelledError
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            lifecycle = RegistryClient(card, 'http://registry', tmp_path / 'key', http, sleep=sleep)
            with pytest.raises(asyncio.CancelledError):
                await lifecycle.run()
            assert lifecycle.registered
            assert calls.count('/v1/agents') == 3  # failed attempt, initial, recovery
            assert calls.count('/v1/agents/weather-1/heartbeat') >= 2
            await lifecycle.unregister()
            assert client.get('/v1/agents/weather-1/status').json()['status'] == 'UNREGISTERED'
    asyncio.run(scenario())


@pytest.mark.parametrize('code', [401, 403, 404, 422])
def test_agent_permanent_errors_do_not_spin(tmp_path, card, code):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(code))) as http:
            lifecycle = RegistryClient(card, 'http://registry', tmp_path / 'key', http)
            await lifecycle.run()
            assert lifecycle.state == 'operator_required'
    asyncio.run(scenario())


def test_weather_lifespan_unregister_and_business_survives_registry_failure(monkeypatch, tmp_path):
    from demo import weather_agent
    from fastapi.testclient import TestClient
    real_client = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503)
    monkeypatch.setenv('WEATHER_CREDENTIAL_FILE', str(tmp_path / 'key'))
    monkeypatch.setattr(weather_agent.httpx, 'AsyncClient', lambda **kw:
                        real_client(transport=httpx.MockTransport(handler), **kw))
    with TestClient(weather_agent.app) as client:
        assert client.get('/forecast').status_code == 200
        assert client.get('/health').json()['ready'] is True
    assert '/v1/agents' in calls
