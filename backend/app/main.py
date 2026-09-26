from contextlib import asynccontextmanager
from pathlib import Path
import threading
import shutil
import os
from starlette.concurrency import run_in_threadpool

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
        if engine.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(741993821)'))
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.serverless and not settings.testing and not settings.temporary_session:
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise ValueError('Supabase private storage is required for serverless deployment.')
        if not settings.database_url.startswith('postgresql'):
            raise ValueError('Serverless deployment requires persistent PostgreSQL.')
        if settings.max_upload_mb > 3 or settings.max_pages > 30:
            raise ValueError('Serverless deployment supports at most 3 MB and 30 pages per file.')
        if settings.embedding_model:
            raise ValueError('Hosted embeddings are disabled in the bounded serverless deployment.')
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith('sqlite:///'):
        Path(settings.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
    engine, sessions = database(settings.database_url, settings.serverless)

    initialization_lock = threading.Lock()
    initialized = False

    def initialize():
        nonlocal initialized
        with initialization_lock:
            if not initialized:
                if settings.auto_migrate:
                    if settings.temporary_session:
                        from .database import Base

                        Base.metadata.create_all(engine)
                    else:
                        migrate(engine)
                initialized = True

    @asynccontextmanager
    async def lifespan(app):
        initialize()
        processor.recover()
        yield
        processor.close()
        engine.dispose()

    app = FastAPI(title='LegalLens', version='0.1.0', lifespan=lifespan)
    processor = Processor(sessions, settings)
    app.state.settings, app.state.sessions, app.state.engine = settings, sessions, engine
    app.state.processor = processor
    from .cloud_runtime import PostgresWorkspaceLocks, PostgresRateLimiter

    cloud_guards = settings.serverless and engine.dialect.name == 'postgresql'
    app.state.workspace_locks = PostgresWorkspaceLocks(engine) if cloud_guards else WorkspaceLocks()
    from .providers import configured_provider

    model_values = (settings.model_base_url, settings.model_api_key, settings.model_name)
    if any(model_values) and not all(model_values):
        raise ValueError(
            'Configure all three LEGALLENS_MODEL_* values, or leave all empty for local extractive mode.'
        )
    app.state.answer_provider = configured_provider(settings)
    app.state.limiter = PostgresRateLimiter(engine) if cloud_guards else RateLimiter()
    app.state.dummy_password = hash_password('unused-timing-equalization-password')
    app.add_middleware(BodyLimitMiddleware, max_bytes=(settings.max_upload_mb + 1) * 1024 * 1024)

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        if settings.serverless and not initialized:
            try:
                await run_in_threadpool(initialize)
            except Exception:
                return JSONResponse(
                    {
                        'detail': 'Database setup could not complete. Check the deployment database connection.'
                    },
                    status_code=503,
                )
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

    from .storage import StorageError

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = ', '.join('.'.join(str(x) for x in err['loc'] if x != 'body') for err in exc.errors())
        return JSONResponse(
            {'detail': f'Invalid input in {fields}. Check the required fields and their length limits.'},
            status_code=422,
        )

    @app.get('/api/capabilities')
    def capabilities():
        return {
            'max_upload_mb': settings.max_upload_mb,
            'ocr_available': not settings.serverless and bool(shutil.which('tesseract')),
            'request_processing': settings.serverless,
        }

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


# The temporary entrypoint creates an isolated app per request, never a global database.
app = None if os.environ.get('LEGALLENS_TEMPORARY_SESSION') == 'true' else create_app()
