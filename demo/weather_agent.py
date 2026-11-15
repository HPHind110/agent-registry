"""Independent service: deterministic weather data, real registry integration."""
import asyncio
from contextlib import asynccontextmanager, suppress
import os

import httpx
from fastapi import FastAPI, Query

from .registry_client import RegistryClient


@asynccontextmanager
async def lifespan(app):
    card = dict(agent_id=os.getenv('WEATHER_AGENT_ID', 'weather-local'), name='Weather Agent',
                domain='weather', description='Deterministic forecast for discovery demonstration',
                capabilities=['weather_forecast'],
                endpoint=os.getenv('WEATHER_ENDPOINT', 'http://127.0.0.1:8001/forecast'), version='1.0')
    async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as http:
        lifecycle = RegistryClient(card, os.getenv('REGISTRY_URL', 'http://127.0.0.1:8000'),
                                   os.getenv('WEATHER_CREDENTIAL_FILE', 'weather.credential'), http,
                                   retry_max=float(os.getenv('AGENT_RETRY_MAX_SECONDS', '10')))
        app.state.lifecycle = lifecycle
        task = asyncio.create_task(lifecycle.run())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            with suppress(TimeoutError):
                await asyncio.wait_for(lifecycle.unregister(), timeout=4)



app = FastAPI(title='Weather Agent', lifespan=lifespan)


@app.get('/forecast')
def forecast(city: str = Query('Hanoi', min_length=1, max_length=100)):
    return {'city': city, 'temperature_c': 26, 'condition': 'partly_cloudy',
            'source': 'demo_static_data'}


@app.get('/health')
def health():
    lifecycle = getattr(app.state, 'lifecycle', None)
    return {'live': True, 'ready': True,
            'registration': lifecycle.state if lifecycle else 'disabled'}
