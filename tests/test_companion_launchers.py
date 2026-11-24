"""Run the downloaded kit against temporary Agent and Registry services."""
import hashlib
import json
import os
import runpy
import shutil
import signal
import subprocess
import sys
from zipfile import ZipFile

import pytest

from scripts.build_companion import ROOT, build_kit
from companion.cli import CONFIG
from test_companion import setup
from test_registry import card, env


@pytest.fixture
def kit(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE" if os.name == "nt" else "HOME", str(tmp_path))
    folder = tmp_path / "Provider kit with spaces"
    with ZipFile(ROOT / "downloads/registry-companion-kit.zip") as archive:
        archive.extractall(folder)
    return folder


def wrapper(folder, name="registry-companion-start"):
    return folder / (name + (".cmd" if os.name == "nt" else ".sh"))


def execute(script, *args, answers="", environ=None):
    if os.name == "nt":
        # cmd /c treats a leading quoted executable specially. Use a relative
        # filename in the kit directory, just as Explorer does on double-click.
        command = [os.environ["COMSPEC"], "/d", "/c", script.name, *args]
    else:
        command = ["/bin/sh", str(script), *args]
    return subprocess.run(command, cwd=script.parent, env=environ, input=answers,
                          capture_output=True, text=True, timeout=20)


def test_release_bundle_reproducible(tmp_path, kit):
    dest = tmp_path / "kit.zip"
    build_kit(dest, ROOT / "downloads/registry-companion.pyz")
    assert dest.read_bytes() == (ROOT / "downloads/registry-companion-kit.zip").read_bytes()
    assert (kit / "registry-companion.pyz").read_bytes() == (ROOT / "downloads/registry-companion.pyz").read_bytes()
    with ZipFile(dest) as archive:
        assert archive.getinfo("registry-companion-start.sh").external_attr >> 16 == 0o100755
    assert b"\r" not in (kit / "registry-companion-start.sh").read_bytes()


def test_native_wrapper_setup_restart_and_drift(kit, setup):
    # check is read-only. An invalid key ends start at the authenticated POST,
    # giving the real foreground CLI a deterministic exit without a live Agent.
    key = "private-fixture-key"
    setup.key.write_text(key)
    config = setup.file.parent / "Dashboard file with spaces.json"
    setup.file.rename(config)
    result = execute(wrapper(kit), answers=f'"{config}"\n{setup.api.health_url}\n')
    assert result.returncode == 2 and "Profile saved" in result.stdout, result
    assert [r[0] for r in setup.requests] == ["GET", "GET", "GET", "POST"]
    profile, = kit.glob("*.profile.json")
    script = wrapper(kit, profile.name.removesuffix(".profile.json"))
    assert script.read_bytes() == wrapper(kit).read_bytes()
    assert json.loads(profile.read_text()) == {
        "config": str(config), "health_url": setup.api.health_url,
        "sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
    }
    assert key not in profile.read_text() + script.read_text() + result.stdout + result.stderr
    setup.requests.clear()
    result = execute(script)
    assert result.returncode == 2 and "Dashboard JSON path" not in result.stdout
    assert [r[0] for r in setup.requests] == ["GET", "GET", "POST"]
    config.write_bytes(config.read_bytes() + b" ")
    setup.requests.clear()
    result = execute(script)
    assert result.returncode == 2 and "JSON changed" in result.stderr and not setup.requests
    config.unlink()
    result = execute(script)
    assert result.returncode == 2 and "New setup" in result.stderr and not setup.requests


def test_unhealthy_setup_does_not_replace_existing_profile(kit, setup):
    setup.key.write_text("wrong")
    answers = f"{setup.file}\n{setup.api.health_url}\n"
    execute(wrapper(kit), answers=answers)
    profile, = kit.glob("*.profile.json")
    before = profile.read_bytes()
    setup.healthy = False
    setup.requests.clear()
    result = execute(wrapper(kit), "--setup", answers=answers)
    assert result.returncode == 3 and "Check failed" in result.stderr
    assert [r[0] for r in setup.requests] == ["GET"]
    assert before == profile.read_bytes()


@pytest.mark.parametrize("health", ["http://name:private@localhost/health", "http://localhost/health?token=private"])
def test_secret_urls_are_not_saved_or_logged(kit, setup, health):
    result = execute(wrapper(kit), answers=f"{setup.file}\n{health}\n")
    assert result.returncode == 2 and "credential-free" in result.stderr
    assert "private" not in result.stdout + result.stderr
    assert not list(kit.glob("*.profile.json")) and not setup.requests


def test_multiple_profiles_and_foreground_shutdown(kit, setup, monkeypatch):
    launch = runpy.run_path(str(kit / "registry_companion_launcher.py"))["launch"]
    from test_registry import register
    second = {**{k: setup.data[v] for k, v in CONFIG.items()},
              "agent_id": "other-agent"}
    record, _ = register(setup.web, second)
    second_key = setup.file.with_name("other.credential")
    second_key.write_text(record["credential"])
    second_config = setup.file.with_name("second agent.json")
    second_config.write_text(json.dumps(setup.data | {"AGENT_ID": "other-agent", "AGENT_CREDENTIAL_FILE": second_key.name}))

    # Deliver SIGINT in the same process immediately after a real register.
    load_zip = runpy.run_path
    def load_with_interrupt(path):
        mod = load_zip(path)
        register_agent = mod["API"].register
        def register_then_stop(api, current):
            interval = register_agent(api, current)
            signal.raise_signal(signal.SIGINT)
            return interval
        monkeypatch.setattr(mod["API"], "register", register_then_stop)
        return mod
    monkeypatch.setattr(runpy, "run_path", load_with_interrupt)
    generic = wrapper(kit)
    for file in [setup.file, second_config]:
        replies = iter([str(file), setup.api.health_url])
        monkeypatch.setattr("builtins.input", lambda _: next(replies))
        assert launch(generic, True) == 0
    assert len(list(kit.glob("*.profile.json"))) == 2
    for agent in [setup.data["AGENT_ID"], "other-agent"]:
        script, = kit.glob(f"start-{agent}-*{generic.suffix}")
        setup.requests.clear()
        assert launch(script, False) == 0
        assert setup.requests[-1][:2] == ("POST", f"/v1/agents/{agent}/unregister")
        assert setup.web.get(f"/v1/agents/{agent}").json()["status"] == "UNREGISTERED"


def test_wrapper_without_python(kit, tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    if os.name != "nt":
        (empty / "dirname").symlink_to(shutil.which("dirname"))
    result = execute(wrapper(kit), environ={**os.environ, "PATH": str(empty)}, answers="\n")
    assert result.returncode == 2 and "Python 3.11" in result.stderr
