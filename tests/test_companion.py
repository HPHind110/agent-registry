"""Exercise the portable client against real loopback HTTP and a temporary Registry."""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from companion import cli
from scripts.build_companion import build, ROOT
from test_registry import card, env, register


@contextmanager
def serve(handler):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, headers, body = handler(self)
            data = json.dumps(body).encode()
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_GET

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(2)


@pytest.fixture
def setup(env, card, tmp_path):
    web, clock, _ = env
    record, headers = register(web, card)
    state = SimpleNamespace(requests=[], probes=[], healthy=True, codes=[], redirect=None, web=web, clock=clock)
    def registry(request):
        state.requests.append((request.command, request.path, dict(request.headers)))
        if state.codes:
            return state.codes.pop(0), {}, {}
        if state.redirect:
            return 307, {"Location": state.redirect}, {}
        size = int(request.headers.get("Content-Length", 0))
        r = web.request(request.command, request.path, headers=dict(request.headers), content=request.rfile.read(size))
        return r.status_code, {}, r.json()

    def health(request):
        state.probes.append(dict(request.headers))
        return (200 if state.healthy else 503), {}, {}

    with serve(registry) as origin, serve(health) as provider:
        config_dir = tmp_path / "downloaded"
        config_dir.mkdir()
        key = config_dir / "agent-weather-1.credential"
        key.write_text(record["credential"])
        data = {v: record[k] for k, v in cli.CONFIG.items()}
        data.update(REGISTRY_URL=origin, AGENT_CREDENTIAL_FILE=key.name)
        file = config_dir / "agent-weather-1.json"
        file.write_text(json.dumps(data))
        cfg = cli.Config.load(file)
        state.api = cli.API(cfg, provider + "/statusz", 1)
        state.args = ["--config", str(file), "--health-url", state.api.health_url]
        state.file, state.key, state.data = file, key, data
        yield state


def test_pyz_check_is_read_only_from_other_directory(setup, tmp_path):
    artifact = ROOT / "downloads/registry-companion.pyz"
    build(tmp_path / "a.pyz")
    assert artifact.read_bytes() == (tmp_path / "a.pyz").read_bytes()
    result = subprocess.run([sys.executable, "-I", str(artifact), "check", *setup.args],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and "Ownership requires" in result.stderr
    assert [r[0] for r in setup.requests] == ["GET"]
    assert "Authorization" not in setup.requests[0][2] and "Authorization" not in setup.probes[0]
    assert setup.key.read_text() not in result.stdout + result.stderr


@pytest.mark.parametrize("fault", ["missing-json", "malformed", "bad-id", "bad-url", "bad-caps",
                                   "unknown-secret", "missing-key", "unreadable-key", "invalid-key"])
def test_config_errors(setup, fault):
    if fault == "missing-json":
        setup.file.unlink()
    elif fault == "malformed":
        setup.file.write_text("{")
    elif fault == "invalid-key":
        setup.key.write_bytes(b"bad\nHeader")
    elif fault.startswith(("missing-key", "unreadable-key")):
        setup.key.unlink()
        if fault == "unreadable-key":
            setup.key.mkdir()
    else:
        fields = {"bad-id": {"AGENT_ID": "../other"}, "bad-url": {"REGISTRY_URL": "http://example.org"},
                  "bad-caps": {"AGENT_CAPABILITIES": "echo"}, "unknown-secret": {"TOKEN": "secret-value"}}
        setup.file.write_text(json.dumps(setup.data | fields[fault]))
    with pytest.raises(cli.Problem):
        cli.Config.load(setup.file)


class Timeline:
    """Advance Registry UTC and Companion monotonic time without real sleeps."""
    def __init__(self, setup, end, update):
        self.setup, self.end, self.update = setup, end, update
        self.now = 0
        self.steps = []

    def is_set(self):
        return self.now >= self.end

    def wait(self, delay):
        assert delay > 0 and len(self.steps) < 300
        self.steps.append(delay)
        self.now += delay
        self.setup.clock.advance(delay)
        self.update(self.now)


def calls(s, suffix):
    return [req for req in s.requests if req[0] == "POST" and req[1].endswith(suffix)]


def test_health_threshold_recovery_and_shutdown(setup):
    s = setup
    # One transient failure, several leases of healthy runtime, then a longer outage.
    def change(t):
        s.healthy = t != 4 and not 74 <= t < 96
        if t == 72:
            assert not calls(s, "/unregister")
            assert s.web.get("/v1/agents").json()[0]["status"] == "ONLINE"
        if t == 92:
            assert s.web.get("/v1/agents/weather-1").json()["status"] == "UNREGISTERED"

    timer = Timeline(s, 114, change)
    cli.manage(s.api, timer, 2, 3, clock=lambda: timer.now)
    assert len(calls(s, "/v1/agents")) == 2
    assert len(calls(s, "/heartbeat")) >= 7
    assert len(calls(s, "/unregister")) == 2
    assert s.web.get("/v1/agents/weather-1").json()["status"] == "UNREGISTERED"
    assert all("Authorization" not in headers for headers in s.probes)
    assert all("X-Registry-Join-Token" not in headers for _, _, headers in s.requests)


def test_registry_outage_backoff_then_expired_lease(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(cli.random, "uniform", lambda low, high: high)
    def change(t):
        if t == 2:
            s.codes.extend([429, 408, 503, 500, 503, 503])
    timer = Timeline(s, 85, change)
    cli.manage(s.api, timer, 2, 3, clock=lambda: timer.now)
    # First heartbeat after outage hits real Registry 409, then an authenticated POST.
    assert len(calls(s, "/v1/agents")) == 2
    assert len(calls(s, "/heartbeat")) >= 8
    assert all(req[2].get("Authorization") == "Bearer " + s.key.read_text() for req in calls(s, "/v1/agents"))


def test_missing_and_wrong_ownership(setup, caplog):
    s = setup
    s.api.cfg = replace(s.api.cfg, secret="wrong-credential")
    timer = Timeline(s, 5, lambda _: None)
    with pytest.raises(cli.Problem, match="401"):
        cli.manage(s.api, timer, 2, 3, clock=lambda: timer.now)
    assert not calls(s, "/unregister")
    s.requests.clear()
    s.api.cfg.card["agent_id"] = "never-created"
    s.api.path = "/v1/agents/never-created"
    with pytest.raises(cli.Problem, match="404"):
        cli.manage(s.api, timer, 2, 3, clock=lambda: timer.now)
    assert not calls(s, "/v1/agents")
    assert "wrong-credential" not in caplog.text and s.key.read_text() not in caplog.text


def test_rebinding_requires_operator_workflow(setup):
    s = setup
    headers = {"Authorization": "Bearer " + s.key.read_text()}
    updated = s.web.patch(s.api.path, json={"endpoint": "https://new.test/invoke"}, headers=headers).json()
    timer = Timeline(s, 2, lambda _: None)
    with pytest.raises(cli.Problem, match="differs in endpoint"):
        cli.manage(s.api, timer, 2, 3, clock=lambda: timer.now)
    assert all(method == "GET" for method, _, _ in s.requests)
    s.file.write_text(json.dumps(s.data | {"AGENT_ENDPOINT": updated["endpoint"]}))
    s.api.cfg = cli.Config.load(s.file)
    cli.manage(s.api, timer, 2, 3, clock=lambda: timer.now)
    assert s.web.get(s.api.path).json()["endpoint"] == updated["endpoint"]


def test_unhealthy_during_registry_outage_stops_renewing(setup, monkeypatch):
    s = setup
    beats_before_outage = []
    monkeypatch.setattr(cli.random, "uniform", lambda low, high: high)

    def change(t):
        if t == 12:
            beats_before_outage.extend(calls(s, "/heartbeat"))
            s.healthy = False
            s.codes.extend([503] * 20)
        if t == 48:
            assert s.web.get(s.api.path).json()["status"] == "UNREACHABLE"
            assert calls(s, "/heartbeat") == beats_before_outage
            s.codes.clear()
            s.healthy = True

    timer = Timeline(s, 90, change)
    cli.manage(s.api, timer, 2, 3, clock=lambda: timer.now)
    assert len(calls(s, "/v1/agents")) == 2
    assert s.web.get(s.api.path).json()["status"] == "UNREGISTERED"


def test_check_distinguishes_health_failure_and_registry_network_failure(setup, caplog):
    s = setup
    s.healthy = False
    assert cli.main(["check", *s.args]) == 3
    assert "Agent health unavailable" in caplog.text
    assert all(method == "GET" for method, _, _ in s.requests)
    # Reserve a loopback port without listening; no external network is involved.
    import socket
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{reserved.getsockname()[1]}"
        s.file.write_text(json.dumps(s.data | {"REGISTRY_URL": origin}))
        assert cli.main(["check", *s.args]) == 3
    assert "Registry connection unavailable" in caplog.text


def test_redirects_not_followed_and_local_lock(setup, tmp_path, monkeypatch):
    s = setup
    s.redirect = s.api.health_url
    with pytest.raises(cli.Problem, match="307"):
        s.api.heartbeat()
    assert not s.probes
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with cli.instance_lock(s.api.cfg):
        with pytest.raises(cli.Problem, match="lock"):
            with cli.instance_lock(s.api.cfg):
                pytest.fail("duplicate lock accepted")
    with cli.instance_lock(s.api.cfg):
        pass
