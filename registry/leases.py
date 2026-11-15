from datetime import datetime, timedelta, timezone
from enum import Enum


class Status(str, Enum):
    ONLINE = 'ONLINE'
    SUSPECT = 'SUSPECT'
    UNREACHABLE = 'UNREACHABLE'
    UNREGISTERED = 'UNREGISTERED'


def health_at(agent, now, suspect_seconds):
    if agent.withdrawn:
        return Status.UNREGISTERED
    if now >= agent.lease_expires_at:
        return Status.UNREACHABLE
    if now >= agent.last_heartbeat + timedelta(seconds=suspect_seconds):
        return Status.SUSPECT
    return Status.ONLINE


def utc_now():
    return datetime.now(timezone.utc)


def expires_at(now, ttl_seconds):
    return now + timedelta(seconds=ttl_seconds)


def status_at(expiry, now):
    return 'ACTIVE' if now < expiry else 'EXPIRED'
