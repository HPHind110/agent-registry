"""Observe derived state transitions for logs; discovery never depends on this task."""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .database import Agent
from .leases import health_at


async def observe_health(sessions, settings, clock):
    previous = {}
    log = logging.getLogger('uvicorn.error')
    while True:
        await asyncio.sleep(1)
        try:
            with sessions() as db:
                now = clock()
                current = {a.agent_id: health_at(a, now, settings.suspect_seconds)
                           for a in db.scalars(select(Agent))}
            for agent_id, state in current.items():
                if previous.get(agent_id) != state:
                    log.info('[registry] %s -> %s (heartbeat/lease observation)', agent_id, state.value)
            previous = current
        except SQLAlchemyError:
            log.warning('Health observation unavailable; discovery still evaluates state on request')
