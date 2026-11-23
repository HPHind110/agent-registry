"""Independent service: deterministic weather data, real registry integration."""
from contextlib import asynccontextmanager
import os

import httpx
from fastapi import FastAPI, Query

from agent_registry_client import registered_agent


@asynccontextmanager
async def lifespan(app):
    card = dict(agent_id=os.getenv('WEATHER_AGENT_ID', 'weather-local'), name='Weather Agent',
                domain='weather', description='Deterministic forecast for discovery demonstration',
                capabilities=['weather_forecast'],
                endpoint=os.getenv('WEATHER_ENDPOINT', 'http://127.0.0.1:8001/forecast'), version='1.0')
    async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as http:
        async with registered_agent(card, os.getenv('REGISTRY_URL', 'http://127.0.0.1:8000'),
                                    os.getenv('WEATHER_CREDENTIAL_FILE', 'weather.credential'), http,
                                    join_token=os.getenv('REGISTRY_JOIN_TOKEN'),
                                    retry_max=float(os.getenv('AGENT_RETRY_MAX_SECONDS', '10'))) as lifecycle:
            app.state.lifecycle = lifecycle
            yield



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


from fastapi import HTTPException
from .contracts import Invocation, InvocationResult, WeatherInput, validated_input


@app.post('/forecast', response_model=InvocationResult)
def invoke(request: Invocation):
    if request.capability != 'weather_forecast':
        raise HTTPException(400, detail={'code': 'unsupported_capability'})
    data = validated_input(WeatherInput, request.input)
    return {'agent_id': os.getenv('WEATHER_AGENT_ID', 'weather-local'),
            'capability': request.capability, 'output': forecast(data.city)}
