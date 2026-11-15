from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, String, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError('Timezone-aware datetime required')
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = 'agents'
    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1000))
    capabilities: Mapped[list[str]] = mapped_column(JSON)
    endpoint: Mapped[str] = mapped_column(String(2048))
    version: Mapped[str] = mapped_column(String(64))
    credential_hash: Mapped[str] = mapped_column(String(64))
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_heartbeat: Mapped[datetime] = mapped_column(UTCDateTime())
    lease_expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


def create_database(url):
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 10})
    Base.metadata.create_all(engine)
    # Additive migration for existing SQLite databases; never rewrite leases/keys.
    with engine.begin() as connection:
        if 'withdrawn' not in {c['name'] for c in inspect(connection).get_columns('agents')}:
            connection.execute(text('ALTER TABLE agents ADD COLUMN withdrawn BOOLEAN NOT NULL DEFAULT 0'))
    return engine, sessionmaker(engine, expire_on_commit=False)
