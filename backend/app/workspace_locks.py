import asyncio
from contextlib import asynccontextmanager
from threading import Lock


class WorkspaceLocks:
    """Serialize derived-artifact commits with deletion within the supported single API process."""

    def __init__(self):
        self.guard = Lock()
        self.entries = {}

    @asynccontextmanager
    async def hold(self, workspace_id: str):
        with self.guard:
            entry = self.entries.setdefault(workspace_id, [asyncio.Lock(), 0])
            entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            with self.guard:
                entry[1] -= 1
                if not entry[1]:
                    del self.entries[workspace_id]
