"""Discover a provider, then invoke its advertised endpoint; no weather address."""
import argparse
import os
import sys

import httpx


def fetch_forecast(registry_url, city, client):
    response = client.get(f'{registry_url.rstrip("/")}/v1/agents',
                          params={'capability': 'weather_forecast', 'domain': 'weather'})
    response.raise_for_status()
    providers = response.json()
    if not providers:
        raise RuntimeError('No active weather provider; retry after provider recovery')
    for provider in providers:
        try:
            result = client.get(provider['endpoint'], params={'city': city})
            result.raise_for_status()
            return {'provider_id': provider['agent_id'], 'forecast': result.json()}
        except (httpx.HTTPError, ValueError):
            # An ACTIVE lease is not a guarantee of reachability. Try the next provider.
            continue
    raise RuntimeError('All discovered weather providers are unreachable or returned invalid data')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--city', default='Hanoi')
    args = parser.parse_args()
    try:
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            print(fetch_forecast(os.getenv('REGISTRY_URL', 'http://127.0.0.1:8000'), args.city, client))
    except (httpx.HTTPError, RuntimeError) as exc:
        # Avoid logging endpoint URLs or headers from HTTP exceptions.
        print(str(exc) if isinstance(exc, RuntimeError) else 'Registry HTTP request failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
