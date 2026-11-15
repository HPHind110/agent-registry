from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .schemas import AgentCard, AgentPatch, AgentStatus, AgentView, Health, Registration, normalize
from .service import RegistryError, RegistryService

router = APIRouter(prefix='/v1')
bearer = HTTPBearer(auto_error=False)


def credential(auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    return auth.credentials if auth else None


def service(request: Request):
    with request.app.state.sessions() as session:
        yield RegistryService(session, request.app.state.settings, request.app.state.clock)


@router.post('/agents', response_model=Registration, response_model_exclude_none=True, status_code=201,
             responses={200: {'model': Registration}, 401: {'description': 'Invalid ownership credential'}})
def register(card: AgentCard, response: Response, token=Depends(credential), svc=Depends(service)):
    result, created = svc.register(card, token)
    response.status_code = 201 if created else 200
    response.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/agents', response_model=list[AgentView])
def discover(capability: str | None = Query(None, max_length=100),
             domain: str | None = Query(None, max_length=100),
             active_only: bool = True, svc=Depends(service)):
    try:
        capability = normalize(capability) if capability is not None else None
        domain = normalize(domain) if domain is not None else None
    except ValueError as exc:
        raise RegistryError(422, str(exc)) from exc
    return svc.discover(capability, domain, active_only)


@router.get('/agents/{agent_id}', response_model=AgentView)
def lookup(agent_id: str, svc=Depends(service)):
    return svc.view(svc.get(agent_id))


@router.patch('/agents/{agent_id}', response_model=AgentView)
def patch(agent_id: str, card: AgentPatch, token=Depends(credential), svc=Depends(service)):
    return svc.mutate(agent_id, token, 'patch', card)


@router.post('/agents/{agent_id}/heartbeat', response_model=AgentView)
def heartbeat(agent_id: str, token=Depends(credential), svc=Depends(service)):
    return svc.mutate(agent_id, token, 'heartbeat')


@router.get('/agents/{agent_id}/status', response_model=AgentStatus)
def status(agent_id: str, svc=Depends(service)):
    return svc.view(svc.get(agent_id))


@router.delete('/agents/{agent_id}', status_code=204)
def unregister(agent_id: str, token=Depends(credential), svc=Depends(service)):
    svc.mutate(agent_id, token, 'delete')
    return Response(status_code=204)


@router.post('/agents/{agent_id}/unregister', response_model=AgentView)
def withdraw(agent_id: str, token=Depends(credential), svc=Depends(service)):
    return svc.mutate(agent_id, token, 'unregister')


@router.get('/health', response_model=Health)
def health(svc=Depends(service)):
    try:
        svc.db.execute(text('SELECT 1'))
    except SQLAlchemyError as exc:
        raise RegistryError(503, 'Database unavailable') from exc
    return dict(status='ok', server_time=svc.clock(),
                heartbeat_interval_seconds=svc.settings.heartbeat_seconds, ttl_seconds=svc.settings.ttl_seconds)
