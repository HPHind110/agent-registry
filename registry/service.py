import hashlib
import secrets
import logging

from sqlalchemy import select, text

from .database import Agent
from .leases import expires_at, health_at, Status
from .schemas import AgentCard


class RegistryError(Exception):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class RegistryService:
    def __init__(self, session, settings, clock):
        self.db, self.settings, self.clock = session, settings, clock

    def begin_write(self):
        # Serialize SQLite writers BEFORE reading ownership/lease state.
        self.db.execute(text('BEGIN IMMEDIATE'))

    def get(self, agent_id):
        agent = self.db.get(Agent, agent_id)
        if agent is None:
            raise RegistryError(404, 'Agent not found')
        return agent

    def authorize(self, agent, token):
        if not token or not secrets.compare_digest(digest(token), agent.credential_hash):
            raise RegistryError(401, 'Valid Agent Bearer credential required')

    def view(self, agent, now=None):
        now = now if now is not None else self.clock()
        fields = set(AgentCard.model_fields) | {
            'registered_at', 'updated_at', 'last_heartbeat', 'lease_expires_at'}
        return {**{key: getattr(agent, key) for key in fields},
                'status': health_at(agent, now, self.settings.suspect_seconds)}

    def check_admission(self, supplied):
        expected = self.settings.join_token
        if expected and expected.strip():
            if not supplied or not secrets.compare_digest(digest(supplied), digest(expected)):
                raise RegistryError(403, 'Valid registration join token required')
        elif not self.settings.allow_open_registration:
            raise RegistryError(503, 'New registrations are disabled')

    def register(self, card, token, join_token=None):
        self.begin_write()
        agent = self.db.get(Agent, card.agent_id)
        credential = None
        if agent is not None:
            self.authorize(agent, token)
        elif token is not None:
            raise RegistryError(401, 'Credential does not identify an existing Agent')
        now = self.clock()
        created = agent is None
        if created:
            self.check_admission(join_token)
            credential = secrets.token_urlsafe(32)
            agent = Agent(credential_hash=digest(credential), registered_at=now)
            self.db.add(agent)
        for key, value in card.model_dump(mode='json').items():
            setattr(agent, key, value)
        agent.updated_at = agent.last_heartbeat = now
        agent.withdrawn = False
        agent.lease_expires_at = expires_at(now, self.settings.ttl_seconds)
        self.db.commit()
        logging.getLogger('uvicorn.error').info('Registered %s -> ONLINE; binding updated', agent.agent_id)
        response = self.view(agent, now)
        if credential is not None:
            response['credential'] = credential
        return response | dict(heartbeat_interval_seconds=self.settings.heartbeat_seconds,
                               ttl_seconds=self.settings.ttl_seconds), created

    def discover(self, capability, domain, active_only):
        now = self.clock()
        query = select(Agent).order_by(Agent.agent_id)
        if active_only:
            query = query.where(Agent.lease_expires_at > now)
        if domain is not None:
            query = query.where(Agent.domain == domain)
        agents = self.db.scalars(query).all()
        return [self.view(agent, now) for agent in agents
                if (capability is None or capability in agent.capabilities)
                and (not active_only or health_at(agent, now, self.settings.suspect_seconds) == Status.ONLINE)]

    def mutate(self, agent_id, token, action, patch=None):
        self.begin_write()
        agent = self.get(agent_id)
        self.authorize(agent, token)
        now = self.clock()
        if action == 'heartbeat':
            if agent.withdrawn or now >= agent.lease_expires_at:
                raise RegistryError(409, 'Lease expired; authenticated re-registration required')
            agent.last_heartbeat = agent.updated_at = now
            agent.lease_expires_at = expires_at(now, self.settings.ttl_seconds)
        elif action == 'patch':
            values = {key: getattr(agent, key) for key in AgentCard.model_fields}
            card = AgentCard.model_validate(values | patch.model_dump(exclude_unset=True))
            for key, value in card.model_dump(mode='json').items():
                setattr(agent, key, value)
            agent.updated_at = now
        elif action == 'delete':
            self.db.delete(agent)
        elif action == 'unregister':
            agent.withdrawn = True
            agent.updated_at = now
            agent.lease_expires_at = now
        self.db.commit()
        return None if action == 'delete' else self.view(agent, now)
