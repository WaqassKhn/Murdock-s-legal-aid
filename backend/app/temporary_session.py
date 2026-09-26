"""Request-scoped working files; signed state lives only in browser memory.

SQLite is a disposable computation format here, not persistent storage. Every
request restores a server-authenticated snapshot into a new temporary directory.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .security import validate_origin
from .storage import validate_key

MAX_BODY = 4_000_000
MAX_STATE = 1_800_000
MAX_EXPANDED = 12_000_000
SESSION_SECONDS = 2 * 60 * 60


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def decode(data: str) -> bytes:
    return base64.b64decode(data, validate=True)


def seal(state: dict, secret: bytes) -> str:
    raw = json.dumps(state, separators=(',', ':')).encode()
    if len(raw) > MAX_EXPANDED:
        raise HTTPException(
            413,
            'Temporary session is full. Delete documents or reports, or refresh to start again. This operation was not saved.',
        )
    data = encode(zlib.compress(raw))
    token = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest() + '.' + data
    if len(token) > MAX_STATE:
        raise HTTPException(
            413,
            'Temporary session is full. Delete documents or reports, or refresh to start again. This operation was not saved.',
        )
    return token


def unseal(token: str, secret: bytes) -> dict:
    try:
        if len(token) > MAX_STATE:
            raise ValueError()
        signature, data = token.split('.', 1)
        expected = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        inflater = zlib.decompressobj()
        raw = inflater.decompress(decode(data), MAX_EXPANDED + 1)
        if len(raw) > MAX_EXPANDED or not inflater.eof:
            raise ValueError()
        state = json.loads(raw)
        if not 0 <= time.time() - state['created'] < SESSION_SECONDS:
            raise ValueError()
        return state
    except (ValueError, TypeError, KeyError, zlib.error):
        raise HTTPException(
            400, 'Temporary session is invalid or expired. Refresh to start a new session.'
        ) from None


def create_session_app(secret: str | None = None, settings: Settings | None = None):
    app = FastAPI(title='LegalLens temporary session')
    configured = settings or Settings(_env_file=None)
    secret = secret if secret is not None else os.environ.get('LEGALLENS_SESSION_SECRET', '')

    @app.get('/health')
    def health():
        if len(secret) < 32:
            raise HTTPException(
                503, 'Set LEGALLENS_SESSION_SECRET to a random value of at least 32 characters.'
            )
        return {'status': 'ok', 'storage': 'temporary browser session'}

    @app.get('/api/capabilities')
    def capabilities():
        return {
            'max_upload_mb': 1,
            'ocr_available': False,
            'request_processing': True,
            'temporary_session': True,
        }

    @app.post('/api/session')
    async def session(request: Request):
        health()
        if not validate_origin(request, ''):
            raise HTTPException(403, 'Cross-origin request rejected.')
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > MAX_BODY:
                raise HTTPException(
                    413, 'Request exceeds the temporary session limit. Use a smaller file (maximum 1 MB).'
                )
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError()
            path = payload['path']
            method = payload.get('method', 'GET')
            if (
                not isinstance(path, str)
                or not path.startswith('/api/')
                or '?' in path
                or '#' in path
                or '..' in path
                or '\\' in path
            ):
                raise ValueError()
            if method not in {'GET', 'POST', 'PATCH', 'DELETE', 'PUT'}:
                raise ValueError()
            content = decode(payload.get('body', ''))
            content_type = payload.get('content_type', 'application/json')
            if (
                not isinstance(content_type, str)
                or len(content_type) > 256
                or '\r' in content_type
                or '\n' in content_type
            ):
                raise ValueError()
            token = payload.get('state', '')
            if not isinstance(token, str):
                raise ValueError()
            state = unseal(token, secret.encode()) if token else {'created': time.time(), 'files': {}}
        except (ValueError, TypeError, KeyError):
            raise HTTPException(400, 'Invalid session request.') from None

        with TemporaryDirectory(prefix='legallens-') as directory:
            root = Path(directory)
            files = root / 'files'
            files.mkdir()
            if 'database' in state:
                (root / 'session.db').write_bytes(decode(state['database']))
            for name, value in state['files'].items():
                (files / validate_key(name)).write_bytes(decode(value))
            # Explicitly override storage/limits: old deployment env values cannot
            # accidentally turn this into local persistence or external storage.
            isolated = configured.model_copy(
                update={
                    'database_url': f'sqlite:///{root / "session.db"}',
                    'storage_dir': files,
                    'serverless': True,
                    'temporary_session': True,
                    'supabase_url': '',
                    'supabase_secret_key': '',
                    'embedding_model': '',
                    'max_upload_mb': 1,
                    'max_pages': 30,
                    'max_workspace_documents': 6,
                    'auto_migrate': True,
                    'secure_cookies': True,
                }
            )
            from .main import create_app

            inner = await run_in_threadpool(create_app, isolated)
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=inner), base_url=str(request.base_url)
                ) as client:
                    result = await client.request(
                        method,
                        path,
                        content=content,
                        headers={
                            'content-type': content_type,
                            'cookie': request.headers.get('cookie', ''),
                        },
                    )
                inner.state.engine.dispose()
                state['database'] = encode((root / 'session.db').read_bytes())
                state['files'] = {p.name: encode(p.read_bytes()) for p in files.iterdir() if p.is_file()}
                response = JSONResponse(
                    {
                        'status': result.status_code,
                        'headers': {
                            k: v
                            for k, v in result.headers.items()
                            if k in {'content-type', 'content-disposition'}
                        },
                        'body': encode(result.content),
                        'state': seal(state, secret.encode()),
                    }
                )
                if len(response.body) > MAX_BODY:
                    raise HTTPException(
                        413,
                        'Response exceeds the session limit. Delete some documents or reports and retry. This operation was not saved.',
                    )
                for cookie in result.headers.get_list('set-cookie'):
                    response.headers.append('set-cookie', cookie)
                response.headers['Cache-Control'] = 'no-store'
                return response
            finally:
                inner.state.processor.close()
                inner.state.engine.dispose()

    return app
