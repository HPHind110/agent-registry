"""Deterministic aggregation; discovery and invocation live in reusable modules."""
import argparse
import json
import os
import httpx
from agent_registry_client.discovery import DiscoveryError
from agent_registry_client.invocation import invoke_with_rediscovery, InvocationError
from .contracts import WeatherOutput, SearchOutput


def build_plan(registry_url, city, http):
    result = {'city': city, 'weather': None, 'news': [], 'providers_used': [], 'errors': {}}
    for section, capability, domain, data, schema in (
        ('weather', 'weather_forecast', 'weather', {'city': city}, WeatherOutput),
        ('news', 'search_news', 'news', {'keyword': city}, SearchOutput),
    ):
        try:
            output, agent_id = invoke_with_rediscovery(
                http, registry_url, capability, data, schema, domain=domain, safe_to_retry=True,
            )
            result[section] = output['articles'] if section == 'news' else output
            result['providers_used'].append({'agent_id': agent_id, 'capability': capability})
        except DiscoveryError as exc:
            result['errors'][section] = {'stage': 'discovery', 'message': str(exc)}
        except InvocationError as exc:
            result['errors'][section] = {'stage': 'invocation', 'message': str(exc)}
    result['status'] = 'partial' if result['errors'] else 'complete'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--city', default='Hanoi')
    args = parser.parse_args()
    with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as http:
        result = build_plan(os.getenv('REGISTRY_URL', 'http://127.0.0.1:8000'), args.city, http)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
