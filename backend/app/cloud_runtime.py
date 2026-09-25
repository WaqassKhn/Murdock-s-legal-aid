"""Cross-instance guards for request-bound serverless execution."""

import hashlib
import time
from contextlib import asynccontextmanager

from fastapi import HTTPException
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool


def lock_key(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big', signed=True)


class PostgresWorkspaceLocks:
    def __init__(self, engine):
        self.engine = engine

    @asynccontextmanager
    async def hold(self, workspace_id: str):
        # Session pooling is required: this connection owns the lock until request completion.
        connection = await run_in_threadpool(self.engine.connect)
        locked = False
        key = lock_key(workspace_id)
        try:
            locked = await run_in_threadpool(
                connection.scalar, text('SELECT pg_try_advisory_lock(:key)'), {'key': key}
            )
            if not locked:
                raise HTTPException(
                    409, 'Another operation is running in this workspace. Please retry shortly.'
                )
            yield
        finally:
            try:
                if locked:
                    await run_in_threadpool(
                        connection.execute, text('SELECT pg_advisory_unlock(:key)'), {'key': key}
                    )
            finally:
                await run_in_threadpool(connection.close)


class PostgresRateLimiter:
    def __init__(self, engine):
        self.engine = engine

    def check(self, key: str, maximum: int):
        bucket = int(time.time()) // 60
        digest = hashlib.sha256(key.encode()).hexdigest()
        with self.engine.begin() as connection:
            connection.execute(text('DELETE FROM request_limits WHERE "window" < :old'), {'old': bucket - 2})
            count = connection.scalar(
                text(
                    'INSERT INTO request_limits (key, "window", count) VALUES (:key, :window, 1) '
                    'ON CONFLICT (key, "window") DO UPDATE SET count = request_limits.count + 1 RETURNING count'
                ),
                {'key': digest, 'window': bucket},
            )
        if count > maximum:
            raise HTTPException(
                429, 'Too many requests. Please wait one minute and try again.', headers={'Retry-After': '60'}
            )
