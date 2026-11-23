import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = 'sqlite:///./registry.db'
    ttl_seconds: int = 30
    heartbeat_seconds: int = 10
    suspect_seconds: float | None = None

    join_token: str | None = field(default=None, repr=False)
    allow_open_registration: bool = False

    def __post_init__(self):
        if not 0 < self.heartbeat_seconds < self.ttl_seconds:
            raise ValueError('Require 0 < heartbeat_seconds < ttl_seconds')
        if self.suspect_seconds is None:
            object.__setattr__(self, 'suspect_seconds', (self.heartbeat_seconds + self.ttl_seconds) / 2)
        if not self.heartbeat_seconds < self.suspect_seconds < self.ttl_seconds:
            raise ValueError('Require heartbeat < suspect < TTL')

    @classmethod
    def from_env(cls):
        return cls(
            join_token=os.environ.get('REGISTRY_JOIN_TOKEN'),
            allow_open_registration=os.getenv('REGISTRY_ALLOW_OPEN_REGISTRATION') == '1',
            database_url=os.getenv('REGISTRY_DATABASE_URL', 'sqlite:///./registry.db'),
            ttl_seconds=int(os.getenv('REGISTRY_TTL_SECONDS', '30')),
            heartbeat_seconds=int(os.getenv('REGISTRY_HEARTBEAT_SECONDS', '10')),
            suspect_seconds=float(os.environ['REGISTRY_SUSPECT_SECONDS']) if 'REGISTRY_SUSPECT_SECONDS' in os.environ else None,
        )
