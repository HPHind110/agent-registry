"""Real loopback HTTP + independent processes. Uses an isolated temporary DB."""
import os
import secrets
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def eventually(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    raise AssertionError('HTTP smoke condition timed out')


def start(module, port, env):
    control = Path(env['SMOKE_CONTROL_DIR']) / (uuid.uuid4().hex + '.control')
    logfile = control.with_suffix('.log')
    with logfile.open('w') as output:
        process = subprocess.Popen([sys.executable, '-m', 'scripts.smoke_server', module,
                                    str(port), str(control)], cwd=ROOT, env=env,
                                   stdout=output, stderr=output,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    process.control, process.logfile = control, logfile
    return process


def stop(process, graceful=False):
    if process.poll() is None:
        process.control.write_text('stop' if graceful else 'crash')
        process.wait(timeout=15)


def main():
    registry_port, weather_port = free_port(), free_port()
    while weather_port == registry_port:
        weather_port = free_port()
    base = f'http://127.0.0.1:{registry_port}'
    processes = []
    with tempfile.TemporaryDirectory(prefix='registry-smoke-') as directory:
        env = os.environ | {
            'REGISTRY_JOIN_TOKEN': secrets.token_urlsafe(32), 'SMOKE_CONTROL_DIR': directory,
            'REGISTRY_DATABASE_URL': f'sqlite:///{Path(directory).as_posix()}/registry.db',
            'REGISTRY_SUSPECT_SECONDS': '2', 'REGISTRY_TTL_SECONDS': '3', 'REGISTRY_HEARTBEAT_SECONDS': '1',
            'REGISTRY_URL': base, 'WEATHER_AGENT_ID': 'smoke-weather',
            'WEATHER_ENDPOINT': f'http://127.0.0.1:{weather_port}/forecast',
            'WEATHER_CREDENTIAL_FILE': str(Path(directory) / 'weather.credential')}
        try:
            registry = start('registry.main:app', registry_port, env)
            processes.append(registry)
            with httpx.Client(timeout=1, trust_env=False) as client:
                eventually(lambda: client.get(base + '/v1/health').status_code == 200)
                weather = start('demo.weather_agent:app', weather_port, env)
                processes.append(weather)
                eventually(lambda: len(client.get(base + '/v1/agents').json()) == 1)
                initial = client.get(base + '/v1/agents/smoke-weather').json()
                eventually(lambda: client.get(base + '/v1/agents/smoke-weather').json()['last_heartbeat']
                           != initial['last_heartbeat'])

                def travel():
                    return subprocess.run([sys.executable, '-m', 'demo.travel_client', '--city', 'Hanoi'],
                                          env=env, cwd=ROOT, capture_output=True, text=True, timeout=15)

                time.sleep(7)  # Multiple short lease cycles with no browser open.
                assert client.get(base + '/v1/agents/smoke-weather/status').json()['status'] == 'ONLINE'
                result = travel()
                assert result.returncode == 0, result.stderr
                assert 'smoke-weather' in result.stdout
                print('PASS startup, registration, heartbeat, discovery, provider HTTP invocation')
                stop(weather)
                eventually(lambda: client.get(base + '/v1/agents/smoke-weather/status').json()['status'] == 'SUSPECT')
                eventually(lambda: client.get(base + '/v1/agents').json() == [])
                eventually(lambda: client.get(base + '/v1/agents/smoke-weather/status').json()['status'] == 'UNREACHABLE')
                assert travel().returncode == 1
                print('PASS stopped provider expires and disappears from discovery')
                stop(registry)
                registry = start('registry.main:app', registry_port, env)
                processes.append(registry)
                eventually(lambda: client.get(base + '/v1/health').status_code == 200)
                assert client.get(base + '/v1/agents').json() == []
                assert client.get(base + '/v1/agents/smoke-weather/status').json()['status'] == 'UNREACHABLE'
                weather_port = free_port()
                env['WEATHER_ENDPOINT'] = f'http://127.0.0.1:{weather_port}/forecast'
                weather = start('demo.weather_agent:app', weather_port, env)
                processes.append(weather)
                eventually(lambda: len(client.get(base + '/v1/agents').json()) == 1)
                assert client.get(base + '/v1/agents').json()[0]['endpoint'] == env['WEATHER_ENDPOINT']
                assert travel().returncode == 0
                print('PASS database restart retains expiry; authenticated provider recovery')
                stop(registry)
                time.sleep(4)
                assert client.get(f'http://127.0.0.1:{weather_port}/forecast').status_code == 200
                registry = start('registry.main:app', registry_port, env)
                processes.append(registry)
                eventually(lambda: len(client.get(base + '/v1/agents').json()) == 1)
                assert travel().returncode == 0
                print('PASS Registry outage; business API survives; automatic reconnect')
                stop(weather, graceful=True)
                assert client.get(base + '/v1/agents/smoke-weather/status').json()['status'] == 'UNREGISTERED'
                assert client.get(base + '/v1/agents').json() == []
                print('PASS graceful shutdown unregisters immediately')
        except Exception:
            for process in processes:
                print(process.logfile.read_text(errors='replace')[-5000:])
            raise
        finally:
            errors = []
            for process in reversed(processes):
                try:
                    stop(process)
                except Exception as exc:
                    errors.append(exc)
            if errors:
                raise RuntimeError('Smoke process cleanup failed') from errors[0]
    print('PASS process shutdown and temporary database cleanup')


if __name__ == '__main__':
    main()
