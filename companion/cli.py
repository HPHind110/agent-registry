"""Standalone attach-mode client for the Agent Registry v1 protocol (Python 3.11+)."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import http.client
import ipaddress
import json
import logging
import math
import os
from pathlib import Path
import random
import re
import signal
import ssl
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request

LOG = logging.getLogger("registry-companion")
FIELDS = ("agent_id", "name", "domain", "description", "capabilities", "endpoint", "version")
CONFIG = {k: "AGENT_" + k.upper() if k != "agent_id" else "AGENT_ID" for k in FIELDS}
LABEL = re.compile(r"[a-z0-9][a-z0-9_.:]{0,99}")


class Problem(Exception):
    """Operator action is needed. Messages must not include input values."""


class Temporary(Problem):
    """Transport or service may recover without operator action."""


class Expired(Problem):
    """A heartbeat received 409."""


def validate_url(value, *, registry=False):
    try:
        u = urlsplit(value)
        port = u.port
        if (not isinstance(value, str) or not value.isascii() or
                any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value or
                u.scheme not in ("http", "https") or not u.hostname or
                u.username is not None or u.password is not None or u.fragment):
            raise ValueError
        if registry:
            if u.query or u.path.strip("/"):
                raise ValueError
            host = u.hostname
            if u.scheme == "http" and host != "localhost" and not ipaddress.ip_address(host).is_loopback:
                raise ValueError
            authority = f"[{host}]" if ":" in host else host
            if port is not None and port != (443 if u.scheme == "https" else 80):
                authority += f":{port}"
            return f"{u.scheme}://{authority}"
    except (AttributeError, TypeError, ValueError, UnicodeError):
        raise Problem("Invalid URL. Registry requires a trusted HTTPS origin or HTTP loopback.") from None
    return value


@dataclass
class Config:
    origin: str
    card: dict
    secret: str = field(repr=False)

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or set(data) != set(CONFIG.values()) | {"REGISTRY_URL", "AGENT_CREDENTIAL_FILE"}:
                raise ValueError
            card = {k: data[v] for k, v in CONFIG.items()}
            for key, limit in (("agent_id", 128), ("name", 200), ("version", 64), ("description", 1000)):
                v = card[key]
                if not isinstance(v, str) or len(v) > limit or (key != "description" and not v.strip()):
                    raise ValueError
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", card["agent_id"]) or not LABEL.fullmatch(card["domain"]):
                raise ValueError
            caps = card["capabilities"]
            if not isinstance(caps, list) or not 1 <= len(caps) <= 100 or not all(LABEL.fullmatch(v) for v in caps):
                raise ValueError
            if len(set(caps)) != len(caps) or len(card["endpoint"]) > 2048:
                raise ValueError
            validate_url(card["endpoint"])
            origin = validate_url(data["REGISTRY_URL"], registry=True)
            credential_path = path.parent / data["AGENT_CREDENTIAL_FILE"]
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            raise Problem("Cannot read Dashboard JSON or invalid Agent Card fields.") from None
        try:
            if not credential_path.is_file():
                raise ValueError
            with credential_path.open("rb") as handle:
                raw = handle.read(4097)
            secret = raw.rstrip(b"\r\n")
            if len(raw) > 4096 or not re.fullmatch(rb"[A-Za-z0-9_-]+", secret):
                raise ValueError
        except (OSError, ValueError):
            raise Problem("Credential file missing, unreadable or invalid. Check its path relative to the JSON.") from None
        return cls(origin, card, secret.decode("ascii"))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class API:
    def __init__(self, cfg, health_url, timeout):
        self.cfg = cfg
        self.health_url = validate_url(health_url)
        self.timeout = timeout
        self.path = "/v1/agents/" + cfg.card["agent_id"]
        self.http = build_opener(ProxyHandler({}), NoRedirect())

    def healthy(self):
        # A dedicated request never inherits Registry headers, even on the same host.
        try:
            with self.http.open(self.health_url, timeout=self.timeout) as r:
                return 200 <= r.status < 300
        except HTTPError as exc:
            exc.close()
        except (OSError, http.client.HTTPException):
            pass
        return False

    def registry(self, path, *, write=False, card=None, timeout=None):
        headers = {"Accept": "application/json"}
        if write:
            headers["Authorization"] = "Bearer " + self.cfg.secret
        body = None
        if card is not None:
            body = json.dumps(card).encode()
            headers["Content-Type"] = "application/json"
        request = Request(self.cfg.origin + path, data=body, headers=headers, method="POST" if write else "GET")
        try:
            with self.http.open(request, timeout=timeout or self.timeout) as response:
                if response.status != 200:
                    raise Problem("Unexpected Registry status. Check Registry URL and API version.")
                raw = response.read(131073)
                if len(raw) > 131072:
                    raise ValueError
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError
                return result
        except HTTPError as exc:
            code = exc.code
            exc.close()
            if code == 409 and path.endswith("/heartbeat"):
                raise Expired("Lease expired; re-checking card.") from None
            if code in (408, 429) or 500 <= code < 600:
                raise Temporary(f"Registry HTTP {code}; retry later.") from None
            hint = {401: "Check ownership credential for this ID.", 404: "ID missing; register on Dashboard.",
                    403: "Check Registry access and existing identity."}
            raise Problem(f"Registry HTTP {code}. " + hint.get(code, "Check URL and card; redirects are refused.")) from None
        except URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise Problem("Registry TLS verification failed; check hostname and certificate.") from None
            raise Temporary("Registry connection unavailable.") from None
        except (OSError, http.client.HTTPException):
            raise Temporary("Registry connection interrupted.") from None
        except (ValueError, RecursionError):
            raise Problem("Invalid Registry JSON; check URL and API version.") from None

    def lookup(self):
        record = self.registry(self.path)
        for k, expected in self.cfg.card.items():
            got = record.get(k)
            if k == "capabilities" and isinstance(got, list) and all(isinstance(x, str) for x in got):
                got, expected = sorted(got), sorted(expected)
            if got != expected:
                raise Problem(f"Registry card differs in {k}. Review Dashboard and update config before starting.")
        return {k: record[k] for k in FIELDS}

    def register(self, current):
        record = self.registry("/v1/agents", write=True, card=current)
        self.confirm(record, "ONLINE")
        interval, ttl = record.get("heartbeat_interval_seconds"), record.get("ttl_seconds")
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (interval, ttl)) or not 0 < interval < ttl:
            raise Problem("Invalid heartbeat interval or TTL from Registry.")
        return interval

    def confirm(self, record, status):
        if record.get("agent_id") != self.cfg.card["agent_id"] or record.get("status") != status:
            raise Problem("Registry response did not confirm identity and expected status.")

    def heartbeat(self):
        self.confirm(self.registry(self.path + "/heartbeat", write=True), "ONLINE")

    def withdraw(self):
        self.confirm(self.registry(self.path + "/unregister", write=True, timeout=min(self.timeout, 3)), "UNREGISTERED")
        LOG.info("Registration withdrawn; identity retained.")


@contextmanager
def instance_lock(cfg):
    # Per-user directory; OS releases the file lock when the process exits.
    folder = Path.home() / ".registry-companion" / "locks"
    identity = (cfg.origin + "/" + cfg.card["agent_id"]).encode()
    try:
        folder.mkdir(parents=True, mode=0o700, exist_ok=True)
        lock = (folder / (hashlib.sha256(identity).hexdigest() + ".lock")).open("a+b")
    except OSError:
        raise Problem("Cannot open local instance lock; check home directory permissions.") from None
    with lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Problem("Cannot acquire lock; another Companion may already manage this Agent.") from None
        yield


def shutdown(api):
    # DNS and some OS socket operations can outlast a socket timeout.
    def attempt():
        try:
            api.withdraw()
        except Problem as exc:
            LOG.warning("Shutdown unregister failed: %s Lease will expire.", exc)

    thread = threading.Thread(target=attempt, daemon=True)
    thread.start()
    thread.join(min(api.timeout, 3) + 0.5)
    if thread.is_alive():
        LOG.warning("Shutdown unregister timed out; lease will expire.")


def manage(api, stop, poll, threshold, clock=time.monotonic):
    next_probe = next_write = 0
    health = None
    misses = retries = 0
    # idle includes a Dashboard-created ONLINE lease until a withdrawal succeeds.
    phase = "idle"
    attached = False
    try:
        while not stop.is_set():
            try:
                api.lookup()
                break
            except Temporary as exc:
                delay = min(30, 2 ** min(retries, 5))
                retries += 1
                LOG.warning("%s Waiting for Registry lookup.", exc)
                stop.wait(random.uniform(delay / 2, delay))
        retries = 0
        while not stop.is_set():
            now = clock()
            # Probe at heartbeat time too, even if the configured health poll is slower.
            if now >= next_probe or (health and now >= next_write):
                ok = api.healthy()
                if health != ok:
                    LOG.log(logging.INFO if ok else logging.WARNING,
                            "Agent health: %s", "healthy" if ok else "unavailable; withholding heartbeats")
                health = ok
                misses = 0 if ok else misses + 1
                if misses == threshold and phase != "withdrawn":
                    phase = "idle"  # recovery must re-register even if unregister was lost
                    if not retries:
                        next_write = 0
                next_probe = clock() + poll
            if stop.is_set():
                break
            due = health or (misses >= threshold and phase != "withdrawn")
            if due and clock() >= next_write:
                try:
                    if health:
                        if phase == "active":
                            api.heartbeat()
                            LOG.info("Heartbeat accepted.")
                        else:
                            current = api.lookup()
                            if stop.is_set():
                                break
                            attached = True  # server might accept a POST even if its reply is lost
                            interval = api.register(current)
                            phase = "active"
                            LOG.info("Ownership verified; registration ONLINE (heartbeat every %gs).", interval)
                        next_write = clock() + interval
                    elif misses >= threshold:
                        api.withdraw()
                        phase = "withdrawn"
                        attached = False
                        LOG.info("Waiting for Agent recovery.")
                        next_write = 0
                    retries = 0
                except Expired:
                    phase = "idle"
                    next_write = 0
                except Temporary as exc:
                    # A lost register response must be reconciled with a fresh lookup.
                    delay = min(30, 2 ** min(retries, 5))
                    retries += 1
                    next_write = clock() + random.uniform(delay / 2, delay)
                    LOG.warning("%s Retrying with backoff.", exc)
            due = health or (misses >= threshold and phase != "withdrawn")
            wake = min(next_probe, next_write) if due else next_probe
            delay = wake - clock()
            if delay > 0:
                stop.wait(delay)
    except Problem:
        # Stop writing immediately on ownership rejection or a conflicting card.
        attached = False
        raise
    finally:
        if attached:
            shutdown(api)


def positive(value):
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= 3600:
        raise argparse.ArgumentTypeError("expected seconds in (0, 3600]")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(prog="registry-companion")
    parser.add_argument("command", choices=("check", "start"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--health-url", required=True, help="Explicit Provider health URL returning HTTP 2xx")
    parser.add_argument("--timeout", type=positive, default=3, help="HTTP socket timeout in seconds")
    parser.add_argument("--poll-interval", type=positive, default=2, help="Health polling interval in seconds")
    parser.add_argument("--failure-threshold", type=int, default=3, help="Consecutive failed probes before unregister")
    args = parser.parse_args(argv)
    if args.failure_threshold < 2:
        parser.error("--failure-threshold must be at least 2")
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    try:
        cfg = Config.load(args.config)
        api = API(cfg, args.health_url, args.timeout)
        LOG.info("Configuration and credential file loaded.")
        if args.command == "check":
            api.lookup()
            if not api.healthy():
                raise Temporary("Agent health unavailable. Check the local process and health URL.")
            LOG.info("Registry reachable, card matches and Agent health passed. Ownership requires an authenticated write.")
        else:
            stop = threading.Event()
            with instance_lock(cfg):
                previous = {}
                try:
                    for sig in (signal.SIGINT, signal.SIGTERM):
                        previous[sig] = signal.signal(sig, lambda *_: stop.set())
                    manage(api, stop, args.poll_interval, args.failure_threshold)
                finally:
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)
    except Temporary as exc:
        LOG.warning("%s", exc)
        return 3
    except Problem as exc:
        LOG.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
