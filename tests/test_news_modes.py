from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from demo import news_agent
from test_registry import env


@pytest.mark.parametrize('mode', [None, 'auto'])
def test_news_enters_and_exits_sdk_lifecycle(mode, monkeypatch, tmp_path):
    if mode is None:
        monkeypatch.delenv('NEWS_REGISTRY_MODE', raising=False)
    else:
        monkeypatch.setenv('NEWS_REGISTRY_MODE', mode)
    monkeypatch.setenv('NEWS_AGENT_ID', 'news-auto')
    monkeypatch.setenv('REGISTRY_URL', 'http://registry.test')
    key = tmp_path / 'auto.credential'
    monkeypatch.setenv('NEWS_CREDENTIAL_FILE', str(key))
    events = []

    @asynccontextmanager
    async def lifecycle(card, url, credential_file, http, **options):
        assert (card['agent_id'], url, credential_file) == ('news-auto', 'http://registry.test', str(key))
        events.append('start')
        yield SimpleNamespace(state='registered')
        events.append('stop')

    monkeypatch.setattr(news_agent, 'registered_agent', lifecycle)
    with TestClient(news_agent.app) as news:
        assert news.get('/health').json()['registration'] == 'registered'
    assert events == ['start', 'stop']


def test_manual_standalone_and_external_registration(env, monkeypatch, tmp_path):
    registry, clock, _ = env
    monkeypatch.setenv('NEWS_REGISTRY_MODE', 'manual')
    monkeypatch.setenv('NEWS_AGENT_ID', 'news-manual')
    monkeypatch.delenv('REGISTRY_URL', raising=False)
    key = tmp_path / 'unused.credential'
    monkeypatch.setenv('NEWS_CREDENTIAL_FILE', str(key))
    monkeypatch.setenv('AGENT_RETRY_MAX_SECONDS', 'unused-in-manual')
    sdk = Mock(side_effect=AssertionError('unexpected SDK lifecycle'))
    outbound = Mock(side_effect=AssertionError('unexpected outbound HTTP client'))
    monkeypatch.setattr(news_agent, 'registered_agent', sdk)
    monkeypatch.setattr(news_agent.httpx, 'AsyncClient', outbound)
    with TestClient(news_agent.app, base_url='http://provider.test') as news:
        assert news.get('/health').json() == {'live': True, 'ready': True, 'registration': 'disabled'}
        assert registry.get('/v1/agents?active_only=false').json() == []
        assert news.post('/invoke', json={'capability': 'summarize_news', 'input': {
            'text': 'First sentence. Next.'}}).json()['output'] == {'summary': 'First sentence.'}
        card = dict(agent_id='news-manual', name='News Agent', domain='news', version='1.0',
                    description='Manual REST demo', capabilities=['search_news', 'summarize_news'],
                    endpoint='http://provider.test/invoke')
        registration = registry.post('/v1/agents', json=card)
        assert registration.status_code == 201
        clock.advance(10)
        headers = {'Authorization': 'Bearer ' + registration.json()['credential']}
        heartbeat = registry.post('/v1/agents/news-manual/heartbeat', headers=headers)
        assert heartbeat.status_code == 200
        (provider,) = registry.get('/v1/agents?domain=news&capability=search_news').json()
        response = news.post(provider['endpoint'], json={
            'capability': 'search_news', 'input': {'keyword': 'Hanoi'}})
        assert response.status_code == 200
        assert response.json()['agent_id'] == provider['agent_id']
        assert len(response.json()['output']['articles']) == 2
    assert registry.get('/v1/agents/news-manual').json() == heartbeat.json()
    clock.advance(31)
    assert registry.get('/v1/agents').json() == []
    sdk.assert_not_called()
    outbound.assert_not_called()
    assert not key.exists()


def test_manual_ignores_existing_credential(monkeypatch, tmp_path):
    key = tmp_path / 'existing.credential'
    key.write_bytes(b'\xff')
    monkeypatch.setenv('NEWS_REGISTRY_MODE', 'manual')
    monkeypatch.setenv('NEWS_CREDENTIAL_FILE', str(key))
    original_getenv = news_agent.os.getenv

    def getenv(name, default=None):
        assert name != 'NEWS_CREDENTIAL_FILE', 'manual mode accessed credential configuration'
        return original_getenv(name, default)

    monkeypatch.setattr(news_agent.os, 'getenv', getenv)
    with TestClient(news_agent.app) as news:
        assert news.get('/health').json()['ready']
    assert key.read_bytes() == b'\xff'


@pytest.mark.parametrize('value', ['', 'manul'])
def test_invalid_mode_fails_at_startup(monkeypatch, value):
    monkeypatch.setenv('NEWS_REGISTRY_MODE', value)
    with pytest.raises(ValueError, match="NEWS_REGISTRY_MODE must be 'auto' or 'manual'"):
        with TestClient(news_agent.app):
            pass
