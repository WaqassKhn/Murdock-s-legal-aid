from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api import router
from .action_plan import router as action_plan_router
from .config import Settings
from .database import database
from .jobs import Processor
from .security import RateLimiter, hash_password, validate_origin
from .request_limits import BodyLimitMiddleware
from .workspace_locks import WorkspaceLocks


def migrate(engine):
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith('sqlite:///'):
        Path(settings.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
    engine, sessions = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        if settings.auto_migrate:
            migrate(engine)
        processor.recover()
        yield
        processor.close()
        engine.dispose()

    app = FastAPI(title='LegalLens', version='0.1.0', lifespan=lifespan)
    processor = Processor(sessions, settings)
    app.state.settings, app.state.sessions, app.state.engine = settings, sessions, engine
    app.state.processor = processor
    app.state.workspace_locks = WorkspaceLocks()
    from .providers import OpenAICompatibleProvider

    model_values = (settings.model_base_url, settings.model_api_key, settings.model_name)
    if any(model_values) and not all(model_values):
        raise ValueError(
            'Configure all three LEGALLENS_MODEL_* values, or leave all empty for local extractive mode.'
        )
    app.state.answer_provider = OpenAICompatibleProvider(*model_values) if all(model_values) else None
    app.state.limiter = RateLimiter()
    app.state.dummy_password = hash_password('unused-timing-equalization-password')
    app.add_middleware(BodyLimitMiddleware, max_bytes=(settings.max_upload_mb + 1) * 1024 * 1024)

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        if request.method in {'POST', 'PATCH', 'DELETE', 'PUT'} and not validate_origin(
            request, settings.allowed_origins
        ):
            return JSONResponse(
                {'detail': 'Cross-origin request rejected. Open LegalLens from its configured address.'},
                status_code=403,
            )
        # Reject grossly oversized bodies before multipart parsing. The reverse proxy also limits streamed bodies.
        length = request.headers.get('content-length')
        if length and (not length.isdigit() or int(length) > (settings.max_upload_mb + 1) * 1024 * 1024):
            return JSONResponse(
                {'detail': f'Request exceeds the {settings.max_upload_mb} MB file limit.'}, status_code=413
            )
        try:
            response = await call_next(request)
        except Exception:
            # Never send parser/provider exceptions or source text to clients or logs.
            return JSONResponse(
                {
                    'detail': 'The request could not complete. Please retry; your saved documents are unchanged.'
                },
                status_code=500,
            )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = ', '.join('.'.join(str(x) for x in err['loc'] if x != 'body') for err in exc.errors())
        return JSONResponse(
            {'detail': f'Invalid input in {fields}. Check the required fields and their length limits.'},
            status_code=422,
        )

    @app.get('/health')
    def health():
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status': 'ok'}

    app.include_router(router)
    app.include_router(action_plan_router)
    dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    return app


app = create_app()
