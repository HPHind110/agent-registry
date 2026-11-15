from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from demo.travel_client import fetch_forecast
from registry.config import Settings
from registry.database import Agent
from registry.main import create_app
from registry.schemas import AgentView, Registration


class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def card():
    return dict(agent_id='weather-1', name='Weather', domain='Weather', description='Test',
                capabilities=[' Weather-Forecast ', 'weather_forecast'],
                endpoint='http://localhost:8001/forecast', version='1.0')


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    settings = Settings(database_url=f'sqlite:///{(tmp_path / "registry.db").as_posix()}')
    app = create_app(settings, clock)
    with TestClient(app) as client:
        yield client, clock, settings


def register(client, card):
    response = client.post('/v1/agents', json=card)
    assert response.status_code == 201, response.text
    return response.json(), {'Authorization': f'Bearer {response.json()["credential"]}'}


def test_registration_lookup_schema_and_hash(env, card):
    client, clock, _ = env
    body, _ = register(client, card)
    Registration.model_validate(body)
    assert body['capabilities'] == ['weather_forecast']
    assert body['domain'] == 'weather'
    assert body['status'] == 'ONLINE'
    assert datetime.fromisoformat(body['registered_at']) == clock.now
    assert datetime.fromisoformat(body['lease_expires_at']) == clock.now + timedelta(seconds=30)
    view = client.get('/v1/agents/weather-1').json()
    AgentView.model_validate(view)
    assert 'credential' not in view and 'credential_hash' not in view
    with client.app.state.sessions() as db:
        row = db.scalar(select(Agent))
        assert row.credential_hash == hashlib.sha256(body['credential'].encode()).hexdigest()
        assert row.credential_hash != body['credential']


def test_discovery_multiple_providers_and_filters(env, card):
    client, _, _ = env
    for identifier, domain in [('z', 'weather'), ('a', 'weather'), ('b', 'travel')]:
        register(client, card | {'agent_id': identifier, 'domain': domain})
    response = client.get('/v1/agents', params={'capability': 'WEATHER forecast', 'domain': ' WEATHER '})
    assert [r['agent_id'] for r in response.json()] == ['a', 'z']
    assert len(client.get('/v1/agents').json()) == 3
    assert client.get('/v1/agents?capability=unknown').json() == []
    assert client.get('/v1/agents?domain=unknown').json() == []


def test_heartbeat_expiry_boundary_and_reregistration(env, card):
    client, clock, _ = env
    original, headers = register(client, card)
    clock.advance(10)
    renewed = client.post('/v1/agents/weather-1/heartbeat', headers=headers)
    assert renewed.status_code == 200
    assert datetime.fromisoformat(renewed.json()['lease_expires_at']) == clock.now + timedelta(seconds=30)
    clock.advance(29)
    assert client.get('/v1/agents').json() == []
    assert client.get('/v1/agents/weather-1/status').json()['status'] == 'SUSPECT'
    clock.advance(1)
    assert client.get('/v1/agents').json() == []
    assert client.get('/v1/agents?active_only=false').json()[0]['status'] == 'UNREACHABLE'
    assert client.get('/v1/agents/weather-1/status').json()['status'] == 'UNREACHABLE'
    assert client.post('/v1/agents/weather-1/heartbeat', headers=headers).status_code == 409
    response = client.post('/v1/agents', json=card | {'name': 'Recovered'}, headers=headers)
    assert response.status_code == 200
    assert response.json()['status'] == 'ONLINE'
    assert response.json()['registered_at'] == original['registered_at']
    assert 'credential' not in response.json()
    assert response.json()['name'] == 'Recovered'


def test_patch_does_not_renew_and_delete(env, card):
    client, clock, _ = env
    original, headers = register(client, card)
    clock.advance(31)
    response = client.patch('/v1/agents/weather-1', json={'endpoint': 'http://example.org/new',
                            'capabilities': [' New-Capability ']}, headers=headers)
    assert response.status_code == 200
    assert response.json()['endpoint'] == 'http://example.org/new'
    assert response.json()['capabilities'] == ['new_capability']
    assert response.json()['lease_expires_at'] == original['lease_expires_at']
    assert response.json()['status'] == 'UNREACHABLE'
    assert client.delete('/v1/agents/weather-1', headers=headers).status_code == 204
    assert client.get('/v1/agents/weather-1').status_code == 404


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer wrong'}, {'Authorization': 'Basic abc'}])
def test_duplicate_and_unauthorized_mutation(env, card, headers):
    client, _, _ = env
    original, _ = register(client, card)
    assert client.post('/v1/agents', json=card | {'name': 'hijack'}, headers=headers).status_code == 401
    assert client.patch('/v1/agents/weather-1', json={'name': 'hijack'}, headers=headers).status_code == 401
    assert client.post('/v1/agents/weather-1/heartbeat', headers=headers).status_code == 401
    assert client.delete('/v1/agents/weather-1', headers=headers).status_code == 401
    assert client.get('/v1/agents/weather-1').json()['name'] == original['name']


def test_persistence_and_no_resurrection(env, card):
    client, clock, settings = env
    original, headers = register(client, card)
    with TestClient(create_app(settings, clock)) as restarted:
        assert restarted.get('/v1/agents/weather-1').json()['registered_at'] == original['registered_at']
        assert restarted.post('/v1/agents/weather-1/heartbeat', headers=headers).status_code == 200
    clock.advance(31)
    with TestClient(create_app(settings, clock)) as restarted:
        assert restarted.get('/v1/agents').json() == []
        assert restarted.get('/v1/agents/weather-1').json()['status'] == 'UNREACHABLE'
        assert restarted.post('/v1/agents/weather-1/heartbeat', headers=headers).status_code == 409
        assert restarted.post('/v1/agents', json=card, headers=headers).status_code == 200


@pytest.mark.parametrize('change', [
    {'agent_id': '../x'}, {'name': ' '}, {'domain': '!!!'}, {'capabilities': []},
    {'capabilities': ['']}, {'endpoint': 'ftp://example.org'}, {'endpoint': 'bad'},
    {'endpoint': 'http://user:password@example.org'}, {'endpoint': 'http://example.org/#x'},
    {'version': ''}, {'registered_at': '2026-01-01'}, {'status': 'ONLINE'}])
def test_invalid_registration(env, card, change):
    client, _, _ = env
    assert client.post('/v1/agents', json=card | change).status_code == 422


@pytest.mark.parametrize('patch', [{}, {'name': None}, {'name': ''}, {'agent_id': 'x'},
                                    {'lease_expires_at': '2099'}, {'capabilities': []}, {'endpoint': 'bad'}])
def test_invalid_patch(env, card, patch):
    client, _, _ = env
    _, headers = register(client, card)
    assert client.patch('/v1/agents/weather-1', json=patch, headers=headers).status_code == 422


def test_health_missing_and_openapi(env):
    client, _, _ = env
    assert client.get('/v1/health').json()['status'] == 'ok'
    for suffix in ['', '/status']:
        assert client.get('/v1/agents/missing' + suffix).status_code == 404
    assert client.get('/v1/agents?capability=%21').status_code == 422
    assert client.get('/v1/agents?active_only=maybe').status_code == 422
    assert '/v1/agents/{agent_id}/heartbeat' in client.get('/openapi.json').json()['paths']


def test_concurrent_registration_has_one_owner(env, card):
    client, _, _ = env
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post('/v1/agents', json=card), range(4)))
    assert sorted(r.status_code for r in responses) == [201, 401, 401, 401]


def test_travel_discovers_endpoint_and_fails_over():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.host == 'registry':
            return httpx.Response(200, json=[{'agent_id': 'a', 'endpoint': 'http://down/forecast'},
                                             {'agent_id': 'b', 'endpoint': 'http://dynamic/forecast'}])
        if request.url.host == 'down':
            return httpx.Response(503)
        return httpx.Response(200, json={'city': 'Hanoi'})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_forecast('http://registry', 'Hanoi', client)
    assert result['provider_id'] == 'b'
    assert calls[-1] == 'http://dynamic/forecast?city=Hanoi'


def test_travel_no_provider():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))) as client:
        with pytest.raises(RuntimeError, match='No active'):
            fetch_forecast('http://registry', 'Hanoi', client)


@pytest.mark.parametrize('ttl,heartbeat', [(0, 10), (10, 10), (30, 0)])
def test_settings_validation(ttl, heartbeat):
    with pytest.raises(ValueError):
        Settings(ttl_seconds=ttl, heartbeat_seconds=heartbeat)
