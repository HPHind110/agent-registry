"""Real Registry + Weather + News + Planner processes, isolated state."""
import json
import os
import secrets
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import httpx
from scripts.smoke_test import ROOT, free_port, start, stop, eventually


def main():
    processes = []
    with tempfile.TemporaryDirectory(prefix='generic-registry-') as directory:
        ports = set()
        while len(ports) < 4:
            ports.add(free_port())
        rp, wp, np, new_wp = ports
        base = f'http://127.0.0.1:{rp}'
        env = os.environ | {'REGISTRY_JOIN_TOKEN': secrets.token_urlsafe(32), 'SMOKE_CONTROL_DIR': directory, 'REGISTRY_URL': base,
            'REGISTRY_DATABASE_URL': f'sqlite:///{Path(directory).as_posix()}/registry.db',
            'REGISTRY_HEARTBEAT_SECONDS': '1', 'REGISTRY_SUSPECT_SECONDS': '3', 'REGISTRY_TTL_SECONDS': '5',
            'WEATHER_AGENT_ID': 'smoke-weather', 'NEWS_AGENT_ID': 'smoke-news',
            'WEATHER_ENDPOINT': f'http://127.0.0.1:{wp}/forecast',
            'NEWS_ENDPOINT': f'http://127.0.0.1:{np}/invoke',
            'WEATHER_CREDENTIAL_FILE': str(Path(directory) / 'weather.credential'),
            'NEWS_CREDENTIAL_FILE': str(Path(directory) / 'news.credential')}
        def launch(module, port):
            process = start(module, port, env); processes.append(process); return process
        def planner():
            result = subprocess.run([sys.executable, '-m', 'demo.planner_client'], env=env, cwd=ROOT,
                                    capture_output=True, text=True, timeout=25)
            assert result.returncode in (0, 1), result.stderr
            return json.loads(result.stdout)
        try:
            registry = launch('registry.main:app', rp)
            with httpx.Client(timeout=2, trust_env=False) as http:
                eventually(lambda: http.get(base + '/v1/health').status_code == 200)
                weather = launch('demo.weather_agent:app', wp)
                news = launch('demo.news_agent:app', np)
                eventually(lambda: len(http.get(base + '/v1/agents').json()) == 2)
                time.sleep(11)
                assert planner()['status'] == 'complete'
                print('PASS independent providers, auto-heartbeat over multiple TTLs, Planner direct workflow')
                stop(weather)
                eventually(lambda: http.get(base + '/v1/agents/smoke-weather/status').json()['status'] == 'UNREACHABLE')
                partial = planner()
                assert partial['weather'] is None and partial['news'] and partial['status'] == 'partial'
                print('PASS Weather crash leaves News usable and Planner returns partial result')
                env['WEATHER_ENDPOINT'] = f'http://127.0.0.1:{new_wp}/forecast'
                weather = launch('demo.weather_agent:app', new_wp)
                eventually(lambda: len(http.get(base + '/v1/agents').json()) == 2)
                assert http.get(base + '/v1/agents/smoke-weather').json()['endpoint'] == env['WEATHER_ENDPOINT']
                assert planner()['status'] == 'complete'
                stop(registry)
                time.sleep(6)
                assert http.get(f'http://127.0.0.1:{new_wp}/forecast').status_code == 200
                assert http.post(env['NEWS_ENDPOINT'], json={'capability': 'search_news', 'input': {'keyword': 'Hanoi'}}).status_code == 200
                registry = launch('registry.main:app', rp)
                eventually(lambda: len(http.get(base + '/v1/agents').json()) == 2, timeout=25)
                assert planner()['status'] == 'complete'
                print('PASS dynamic endpoint and both providers recover from Registry outage')
                for process, id in [(weather, 'smoke-weather'), (news, 'smoke-news')]:
                    stop(process, graceful=True)
                    assert http.get(base + '/v1/agents/' + id).json()['status'] == 'UNREGISTERED'
                print('PASS graceful unregister for both providers')
        except Exception:
            for process in processes:
                print(process.logfile.read_text(errors='replace')[-5000:])
            raise
        finally:
            failures = []
            for process in reversed(processes):
                try: stop(process)
                except Exception as exc: failures.append(exc)
            if failures: raise RuntimeError('Cleanup failed') from failures[0]
    print('PASS cleanup')


if __name__ == '__main__':
    main()
