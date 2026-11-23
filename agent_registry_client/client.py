"""Reusable owner-side lifecycle. No browser or provider-specific behavior."""
import asyncio
import logging
import os
import random
from pathlib import Path
from contextlib import asynccontextmanager, suppress

import httpx

log = logging.getLogger('uvicorn.error')


class RegistryClient:
    def __init__(self, card, registry_url, credential_file, http, *, sleep=asyncio.sleep,
                 retry_max=10.0, join_token=None):
        if retry_max <= 0:
            raise ValueError('retry_max must be positive')
        self.card, self.url = card, registry_url.rstrip('/')
        self.path, self.http = Path(credential_file), http
        self.sleep, self.retry_max = sleep, retry_max
        self.token = None
        self.join_token = join_token
        self.registered = False
        self.state = 'starting'
        self.interval = 10

    @property
    def headers(self):
        return {'Authorization': f'Bearer {self.token}'} if self.token else {}

    async def register(self):
        log.info('[agent %s] registering', self.card['agent_id'])
        headers = self.headers
        if not self.token and self.join_token:
            headers['X-Registry-Join-Token'] = self.join_token
        response = await self.http.post(self.url + '/v1/agents', json=self.card, headers=headers,
                                        follow_redirects=False)
        response.raise_for_status()
        body = response.json()
        # Save the one-time credential before interpreting other response fields.
        if 'credential' in body:
            self.token = body['credential']
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(self.token)
        interval = float(body['heartbeat_interval_seconds'])
        if not 0 < interval < float(body['ttl_seconds']):
            raise ValueError('Invalid server timing')
        self.interval = interval
        self.registered = True
        self.state = 'registered'
        log.info('[agent %s] registered; heartbeat every %ss', self.card['agent_id'], interval)

    async def heartbeat(self):
        response = await self.http.post(
            self.url + '/v1/agents/' + self.card['agent_id'] + '/heartbeat', headers=self.headers)
        response.raise_for_status()
        self.state = 'registered'
        log.info('[agent %s] heartbeat accepted', self.card['agent_id'])

    async def unregister(self):
        if not self.token:
            return
        try:
            response = await self.http.post(
                self.url + '/v1/agents/' + self.card['agent_id'] + '/unregister', headers=self.headers)
            response.raise_for_status()
            self.state = 'unregistered'
            log.info('[agent %s] unregistered; identity retained', self.card['agent_id'])
        except httpx.HTTPError:
            log.warning('Shutdown unregister unavailable; lease will expire')

    async def run(self):
        try:
            if self.path.exists():
                self.token = self.path.read_text(encoding='utf-8').strip()
                if not self.token:
                    raise ValueError('Empty credential file')
        except (OSError, ValueError):
            self.state = 'operator_required'
            log.error('Cannot read credential; operator action required')
            return
        failures = 0
        while True:
            try:
                if self.registered:
                    await self.heartbeat()
                else:
                    await self.register()
                failures = 0
                await self.sleep(self.interval)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code == 409 and self.registered:
                    self.registered = False
                    continue
                if code < 500 and code not in (408, 429):
                    self.state = 'operator_required'
                    log.error('Registry rejected lifecycle (%s); operator action required', code)
                    return
                failures += 1
            except httpx.RequestError:
                failures += 1
            except OSError:
                self.state = 'operator_required'
                log.error('Cannot persist credential; operator action required')
                return
            except (ValueError, KeyError, TypeError):
                failures += 1
            if failures:
                self.state = 'reconnecting'
                delay = min(self.retry_max, 2 ** min(failures - 1, 10))
                log.warning('Registry unavailable/invalid response; reconnecting')
                await self.sleep(random.uniform(delay / 2, delay))


@asynccontextmanager
async def registered_agent(card, registry_url, credential_file, http, **options):
    """Framework-neutral lifecycle context; caller owns the HTTP client."""
    client = RegistryClient(card, registry_url, credential_file, http, **options)
    task = asyncio.create_task(client.run())
    try:
        yield client
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        with suppress(TimeoutError):
            await asyncio.wait_for(client.unregister(), timeout=4)
