import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.exc import OperationalError

from .config import Settings
from .database import create_database
from .leases import utc_now
from .routes import router
from .service import RegistryError
from .health import observe_health


def create_app(settings=None, clock=utc_now):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        engine, sessions = create_database(settings.database_url)
        app.state.sessions = sessions
        observer = asyncio.create_task(observe_health(sessions, settings, clock))
        try:
            yield
        finally:
            observer.cancel()
            with suppress(asyncio.CancelledError):
                await observer
            engine.dispose()

    app = FastAPI(title='Agent Registry', version='1.0.0', lifespan=lifespan)
    app.state.settings, app.state.clock = settings, clock

    @app.exception_handler(RegistryError)
    async def registry_error(request: Request, exc: RegistryError):
        headers = {'WWW-Authenticate': 'Bearer'} if exc.code == 401 else None
        return JSONResponse(status_code=exc.code, content={'detail': exc.detail}, headers=headers)

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, exc: OperationalError):
        return JSONResponse(status_code=503, content={'detail': 'Database temporarily unavailable'})

    app.include_router(router)

    @app.get('/', response_class=HTMLResponse, include_in_schema=False)
    def dashboard():
        return (Path(__file__).parent / 'dashboard.html').read_text(encoding='utf-8')

    return app


app = create_app()
