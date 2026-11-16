"""Independent deterministic News provider. No external network business dependencies."""
from contextlib import asynccontextmanager
import os
import re
import httpx
from fastapi import FastAPI, HTTPException
from agent_registry_client import registered_agent
from .contracts import Invocation, InvocationResult, SearchInput, SummaryInput, validated_input

ARTICLES = (
    {'title': 'Hanoi travel update', 'summary': 'Hanoi museums welcome visitors this weekend.'},
    {'title': 'Technology exhibition', 'summary': 'A technology exhibition opens in Hanoi.'},
    {'title': 'Science news', 'summary': 'Students present a new mathematics project.'},
)


@asynccontextmanager
async def lifespan(app):
    card = dict(agent_id=os.getenv('NEWS_AGENT_ID', 'news-agent-01'), name='News Agent',
                domain='news', description='Deterministic local news demonstration',
                capabilities=['search_news', 'summarize_news'], version='1.0',
                endpoint=os.getenv('NEWS_ENDPOINT', 'http://127.0.0.1:8002/invoke'))
    async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as http:
        async with registered_agent(card, os.getenv('REGISTRY_URL', 'http://127.0.0.1:8000'),
                                    os.getenv('NEWS_CREDENTIAL_FILE', 'news.credential'), http,
                                    retry_max=float(os.getenv('AGENT_RETRY_MAX_SECONDS', '10'))) as lifecycle:
            app.state.lifecycle = lifecycle
            yield


app = FastAPI(title='News Agent', lifespan=lifespan)


@app.post('/invoke', response_model=InvocationResult)
def invoke(request: Invocation):
    if request.capability == 'search_news':
        data = validated_input(SearchInput, request.input)
        output = {'articles': [dict(a) for a in ARTICLES
                              if data.keyword.casefold() in (a['title'] + ' ' + a['summary']).casefold()]}
    elif request.capability == 'summarize_news':
        data = validated_input(SummaryInput, request.input)
        # Extract first sentence, bounded to 240 characters; not an AI summarizer.
        output = {'summary': re.split(r'(?<=[.!?])\s+', data.text)[0][:240]}
    else:
        raise HTTPException(400, detail={'code': 'unsupported_capability'})
    return {'agent_id': os.getenv('NEWS_AGENT_ID', 'news-agent-01'),
            'capability': request.capability, 'output': output}


@app.get('/health')
def health():
    lifecycle = getattr(app.state, 'lifecycle', None)
    return {'live': True, 'ready': True,
            'registration': lifecycle.state if lifecycle else 'disabled'}
