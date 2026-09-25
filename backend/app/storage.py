"""Private object storage; callers must authorize access before resolving an object key."""

import re
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from .config import Settings


class StorageError(RuntimeError):
    pass


class ObjectStorage(Protocol):
    def write(self, key: str, content: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def validate_key(key: str) -> str:
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.(?:pdf|docx|txt|md|csv)', key):
        raise ValueError('Invalid internal storage key.')
    return key


class LocalStorage:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()

    def path(self, key: str) -> Path:
        path = self.directory / validate_key(key)
        if path.resolve().parent != self.directory:
            raise ValueError('Invalid internal storage key.')
        return path

    def write(self, key: str, content: bytes) -> None:
        path = self.path(key)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except OSError:
            raise StorageError('Document storage write failed. Please retry.') from None

    def read(self, key: str) -> bytes:
        path = self.path(key)
        try:
            return path.read_bytes()
        except OSError:
            raise StorageError('Document storage read failed. Please retry.') from None

    def delete(self, key: str) -> None:
        path = self.path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise StorageError('Document storage delete failed. Please retry.') from None


class SupabaseStorage:
    def __init__(
        self,
        url: str,
        secret_key: str,
        bucket: str = 'legallens-documents',
        *,
        max_bytes: int = 20 * 1024 * 1024,
        transport: httpx.BaseTransport | None = None,
    ):
        parsed = urlsplit(url)
        if (
            parsed.scheme != 'https'
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ('', '/')
        ):
            raise ValueError('Supabase URL must be an HTTPS project origin without credentials or a path.')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}', bucket):
            raise ValueError('Invalid Supabase bucket name.')
        if not secret_key.startswith(('sb_secret_', 'eyJ')):
            raise ValueError('Supabase storage requires a server secret or legacy service-role key.')
        self.url = url.rstrip('/') + '/storage/v1/object'
        self.bucket = bucket
        self.headers = {'apikey': secret_key}
        # Modern secret keys are not JWTs and must not be sent as Bearer tokens.
        if secret_key.startswith('eyJ'):
            self.headers['Authorization'] = 'Bearer ' + secret_key
        self.max_bytes = max_bytes
        self.transport = transport

    def request(self, operation: str, method: str, suffix: str, **kwargs) -> bytes:
        headers = {**self.headers, **kwargs.pop('headers', {})}
        for attempt in range(2):
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(20, connect=5),
                    follow_redirects=False,
                    transport=self.transport,
                ) as client:
                    with client.stream(method, self.url + suffix, headers=headers, **kwargs) as response:
                        if operation == 'delete' and response.status_code == 404:
                            return b''
                        if response.status_code in (429, 502, 503, 504) and attempt == 0:
                            continue
                        if not response.is_success:
                            break
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            if len(data) + len(chunk) > self.max_bytes:
                                raise StorageError('Document storage response exceeds the supported size.')
                            data.extend(chunk)
                        return bytes(data)
            except httpx.HTTPError:
                if attempt == 0:
                    continue
        raise StorageError(
            f'Document storage {operation} failed. Please retry or check storage configuration.'
        )

    def write(self, key: str, content: bytes) -> None:
        key = validate_key(key)
        if len(content) > self.max_bytes:
            raise StorageError('Document exceeds the supported storage size.')
        # PUT is an idempotent update but cannot create a new object; upsert POST supports both.
        self.request(
            'write',
            'POST',
            f'/{self.bucket}/{key}',
            content=content,
            headers={'x-upsert': 'true', 'Content-Type': 'application/octet-stream'},
        )

    def read(self, key: str) -> bytes:
        return self.request('read', 'GET', f'/authenticated/{self.bucket}/{validate_key(key)}')

    def delete(self, key: str) -> None:
        self.request('delete', 'DELETE', f'/{self.bucket}', json={'prefixes': [validate_key(key)]})


def storage(settings: Settings) -> ObjectStorage:
    url = getattr(settings, 'supabase_url', '')
    secret_key = getattr(settings, 'supabase_secret_key', '')
    if bool(url) != bool(secret_key):
        raise ValueError('Configure both Supabase URL and server secret key for persistent storage.')
    if url:
        return SupabaseStorage(
            url,
            secret_key,
            getattr(settings, 'supabase_bucket', 'legallens-documents'),
            max_bytes=getattr(settings, 'max_upload_mb', 20) * 1024 * 1024,
        )
    return LocalStorage(settings.storage_dir)
