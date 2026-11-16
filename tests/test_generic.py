import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from demo import news_agent, weather_agent
from demo.planner_client import build_plan
from agent_registry_client.discovery import discover, DiscoveryError, Provider
from agent_registry_client.invocation import invoke_first, InvocationError
from demo.contracts import SearchOutput
from test_registry import env, card, register


def test_registry_accepts_independent_domains(env, card):
    client, clock, _ = env
    for id, domain, cap in [('n', 'news', 'search_news'), ('f', 'finance', 'calculate_tax'),
                             ('w', 'weather', 'weather_forecast'), ('n2', 'news', 'search_news')]:
        register(client, card | {'agent_id': id, 'domain': domain, 'capabilities': [cap]})
    assert len(client.get('/v1/agents?capability=search_news&domain=news').json()) == 2
    assert client.get('/v1/agents?capability=search_news&domain=finance').json() == []
    assert client.get('/v1/agents?capability=calculate_tax').json()[0]['agent_id'] == 'f'
    clock.advance(30)
    assert client.get('/v1/agents').json() == []
    for path in Path('registry').glob('*.py'):
        assert 'weather_forecast' not in path.read_text()
        assert 'search_news' not in path.read_text()


@pytest.mark.parametrize('cap,data,status', [
    ('search_news', {'keyword': 'Hanoi'}, 200), ('search_news', {'keyword': 'no_match'}, 200),
    ('summarize_news', {'text': 'First sentence. Second sentence.'}, 200),
    ('unknown', {}, 400), ('search_news', {}, 422), ('search_news', {'keyword': ''}, 422),
    ('search_news', {'keyword': 123}, 422), ('summarize_news', {'text': ' '}, 422),
])
def test_news_contract(cap, data, status):
    client = TestClient(news_agent.app)  # Business tests deliberately do not enter lifespan.
    response = client.post('/invoke', json={'capability': cap, 'input': data})
    assert response.status_code == status
    if status == 200:
        body = response.json()
        assert body['capability'] == cap
        assert 'output' in body
        if cap == 'summarize_news':
            assert body['output']['summary'] == 'First sentence.'


def test_weather_get_and_post_compatible():
    client = TestClient(weather_agent.app)
    old = client.get('/forecast?city=Hanoi').json()
    new = client.post('/forecast', json={'capability': 'weather_forecast', 'input': {'city': 'Hanoi'}})
    assert new.status_code == 200
    assert new.json()['output'] == old
    assert client.post('/forecast', json={'capability': 'search_news', 'input': {}}).status_code == 400
    assert client.post('/forecast', json={'capability': 'weather_forecast', 'input': {'city': ''}}).status_code == 422


@pytest.mark.parametrize('failure', ['network', 'http', 'json', 'schema', 'identity', 'capability'])
def test_consumer_failover(failure):
    def handler(request):
        if request.url.host == 'first':
            if failure == 'network':
                raise httpx.ConnectError('offline', request=request)
            if failure == 'http':
                return httpx.Response(503)
            if failure == 'json':
                return httpx.Response(200, text='not json')
            body = {'agent_id': 'a', 'capability': 'search_news', 'output': {'articles': []}}
            if failure == 'schema': body['output'] = {'unexpected': True}
            if failure == 'identity': body['agent_id'] = 'wrong'
            if failure == 'capability': body['capability'] = 'wrong'
            return httpx.Response(200, json=body)
        return httpx.Response(200, json={'agent_id': 'b', 'capability': 'search_news', 'output': {'articles': []}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        out, id = invoke_first(http, [Provider(agent_id='a', endpoint='http://first/invoke'),
                                     Provider(agent_id='b', endpoint='http://second/invoke')],
                               'search_news', {'keyword': 'Hanoi'}, SearchOutput)
        assert id == 'b'


@pytest.mark.parametrize('broken', [False, True])
def test_planner_direct_calls_and_partial_results(broken, monkeypatch):
    monkeypatch.setenv('WEATHER_AGENT_ID', 'dynamic-weather')
    monkeypatch.setenv('NEWS_AGENT_ID', 'dynamic-news')
    weather, news = TestClient(weather_agent.app), TestClient(news_agent.app)
    calls = []
    def handler(request):
        calls.append((request.method, request.url.host, request.url.path))
        if request.url.host == 'registry':
            assert request.method == 'GET'
            kind = 'weather' if request.url.params['capability'] == 'weather_forecast' else 'news'
            return httpx.Response(200, json=[{'agent_id': 'dynamic-' + kind,
                'endpoint': 'http://' + kind + ('/forecast' if kind == 'weather' else '/invoke')}])
        if request.url.host == 'weather' and broken:
            return httpx.Response(503)
        service = weather if request.url.host == 'weather' else news
        response = service.post(request.url.path, json=json.loads(request.content))
        return httpx.Response(response.status_code, json=response.json())
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = build_plan('http://registry', 'Hanoi', http)
    assert result['news']
    assert result['status'] == ('partial' if broken else 'complete')
    assert len(result['providers_used']) == (1 if broken else 2)
    assert all(method == 'GET' for method, host, _ in calls if host == 'registry')


@pytest.mark.parametrize('body', [{}, None, [{'agent_id': 'x', 'endpoint': 'ftp://bad'}]])
def test_bad_discovery(body):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))) as http:
        with pytest.raises(DiscoveryError):
            discover(http, 'http://registry', 'search_news')


def test_no_provider():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))) as http:
        with pytest.raises(InvocationError, match='No ONLINE'):
            invoke_first(http, discover(http, 'http://registry', 'search_news'), 'search_news', {}, SearchOutput)


def test_sdk_compatibility():
    from demo.registry_client import RegistryClient as old
    from agent_registry_client import RegistryClient as new
    assert old is new
