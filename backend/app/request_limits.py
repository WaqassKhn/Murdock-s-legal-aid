from fastapi.responses import JSONResponse


class BodyLimitMiddleware:
    """Bound streamed bodies before Starlette can spool multipart data to disk."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        limit = self.max_bytes if scope['path'].endswith('/documents') else 64 * 1024
        chunks, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body = message.get('body', b'')
            total += len(body)
            if total > limit:
                return await JSONResponse(
                    {'detail': 'Request body exceeds the configured upload or input limit.'}, status_code=413
                )(scope, receive, send)
            chunks.append(body)
            if not message.get('more_body', False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()

        await self.app(scope, bounded_receive, send)
