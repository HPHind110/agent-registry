import json

import httpx
import pytest

from agent_registry_client.discovery import DiscoveryError
from agent_registry_client.invocation import InvocationError, invoke_with_rediscovery
from demo.contracts import WeatherOutput
from demo.planner_client import build_plan


REGISTRY = 'http://registry'
DISCOVER = REGISTRY + '/v1/agents'
CAP = 'weather_forecast'
CITY = {'city': 'Hanoi'}
FORECAST = dict(CITY, temperature_c=26, condition='sunny', source='demo')
A = {'agent_id': 'weather-01', 'endpoint': 'http://old-provider:8001/forecast'}
MOVED = dict(A, endpoint='http://new-provider:8010/forecast')
B = dict(A, agent_id='weather-02', endpoint='http://other/forecast')


def reply(provider):
    return {'agent_id': provider['agent_id'], 'capability': CAP, 'output': FORECAST}


def run_requests(steps, **options):
    """Consume the exact ordered HTTP trace, including query, payload and auth boundaries."""
    steps = iter(steps)

    def handler(request):
        step = next(steps, None)
        assert step is not None, f'Unexpected extra {request.method}'
        target, outcome = step
        assert str(request.url.copy_with(query=None)) == target
        if target == DISCOVER:
            assert request.method == 'GET'
            assert dict(request.url.params) == {'capability': CAP, 'domain': 'weather', 'active_only': 'true'}
            assert request.headers['Authorization'] == 'Bearer test-only'
        else:
            assert request.method == 'POST'
            assert json.loads(request.content) == {'capability': CAP, 'input': CITY}
            assert 'Authorization' not in request.headers
        if outcome is None:
            raise httpx.ConnectError('sensitive transport detail', request=request)
        if isinstance(outcome, int):
            return httpx.Response(outcome, text='private error details')
        return httpx.Response(200, json=outcome)

    with httpx.Client(transport=httpx.MockTransport(handler),
                      headers={'Authorization': 'Bearer test-only'}) as http:
        try:
            return invoke_with_rediscovery(http, REGISTRY, CAP, CITY, WeatherOutput, domain='weather', **options)
        finally:
            assert next(steps, None) is None, 'Expected HTTP call was skipped'


def test_success_needs_one_lookup_and_one_post():
    assert run_requests([(DISCOVER, [A]), (A['endpoint'], reply(A))], safe_to_retry=True) == (
        FORECAST, A['agent_id'])


@pytest.mark.parametrize(('fresh', 'winner'), [([MOVED], MOVED), ([A, B], B)],
                         ids=['same-id-new-endpoint', 'new-provider'])
def test_rediscovery_tries_only_new_binding(fresh, winner):
    steps = [(DISCOVER, [A]), (A['endpoint'], None), (DISCOVER, fresh),
             (winner['endpoint'], reply(winner))]
    assert run_requests(steps, safe_to_retry=True) == (FORECAST, winner['agent_id'])


def test_unchanged_or_duplicate_bindings_are_never_retried():
    steps = [(DISCOVER, [A, A]), (A['endpoint'], None), (DISCOVER, [A, A])]
    with pytest.raises(InvocationError, match='no new provider binding'):
        run_requests(steps, safe_to_retry=True)


def test_initial_failover_precedes_rediscovery():
    steps = [(DISCOVER, [A, B]), (A['endpoint'], 503), (B['endpoint'], reply(B))]
    assert run_requests(steps, safe_to_retry=True) == (FORECAST, B['agent_id'])


def test_rediscovery_failure_is_distinct_from_initial_discovery_failure():
    with pytest.raises(DiscoveryError, match='Registry discovery failed'):
        run_requests([(DISCOVER, 503)], safe_to_retry=True)
    with pytest.raises(DiscoveryError, match='Rediscovery failed.*HTTP 503') as caught:
        run_requests([(DISCOVER, [A]), (A['endpoint'], 503), (DISCOVER, None)], safe_to_retry=True)
    assert 'sensitive' not in str(caught.value)


@pytest.mark.parametrize('options', [{}, {'safe_to_retry': False}], ids=['default', 'explicit-opt-out'])
def test_unsafe_operation_keeps_initial_failover_only(options):
    with pytest.raises(InvocationError, match='HTTP 503'):
        run_requests([(DISCOVER, [A, B]), (A['endpoint'], None), (B['endpoint'], 503)], **options)


@pytest.mark.parametrize('code', [400, 422])
def test_input_rejection_blocks_rediscovery_even_with_another_transport_error(code):
    with pytest.raises(InvocationError, match=f'HTTP {code}') as caught:
        run_requests([(DISCOVER, [A, B]), (A['endpoint'], code), (B['endpoint'], None)], safe_to_retry=True)
    assert 'private' not in str(caught.value)


def test_empty_initial_discovery_does_not_retry():
    with pytest.raises(InvocationError, match='No ONLINE provider'):
        run_requests([(DISCOVER, [])], safe_to_retry=True)


def test_final_round_validates_and_stops_after_all_fresh_bindings_fail():
    steps = [(DISCOVER, [A]), (A['endpoint'], 503), (DISCOVER, [MOVED, MOVED, B]),
             (MOVED['endpoint'], reply(B)), (B['endpoint'], dict(reply(B), output={}))]
    with pytest.raises(InvocationError, match='after rediscovery failed.*invalid provider response.*HTTP 503'):
        run_requests(steps, safe_to_retry=True)


@pytest.mark.parametrize('rebind', ['weather', 'news'])
def test_planner_recovers_each_read_independently(rebind):
    lookups = {'weather': 0, 'news': 0}

    def handler(request):
        if request.method == 'GET':
            domain = request.url.params['domain']
            lookups[domain] += 1
            host = 'old' if domain == rebind and lookups[domain] == 1 else domain
            return httpx.Response(200, json=[{'agent_id': domain, 'endpoint': f'http://{host}/invoke'}])
        host = request.url.host
        if host == 'old':
            return httpx.Response(503)
        body = {'agent_id': host, 'capability': json.loads(request.content)['capability'],
                'output': FORECAST if host == 'weather' else {'articles': []}}
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        plan = build_plan(REGISTRY, 'Hanoi', http)
    assert plan['status'] == 'complete' and not plan['errors']
    assert [item['agent_id'] for item in plan['providers_used']] == ['weather', 'news']
    assert lookups == {domain: 1 + (domain == rebind) for domain in lookups}
