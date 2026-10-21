"""Pure-ASGI middleware: request IDs, security headers, request body size cap."""

from __future__ import annotations

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"cache-control": b"no-store",
}


class _TooLarge(BaseException):  # noqa: N818 - BaseException so framework body parsers do not swallow it
    pass


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, max_body: int) -> None:
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = rid

        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_body:
            await self._reject(send, rid)
            return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise _TooLarge
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                hdrs = list(message.get("headers", []))
                existing = {k.lower() for k, _ in hdrs}
                for k, v in SECURITY_HEADERS.items():
                    if k not in existing and not (
                        k == b"cache-control" and scope["path"].startswith("/docs")
                    ):
                        hdrs.append((k, v))
                hdrs.append((b"x-request-id", rid.encode()))
                message["headers"] = hdrs
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except _TooLarge:
            if not started:
                await self._reject(send, rid)

    async def _reject(self, send: Send, rid: str) -> None:
        body = (
            b'{"error":{"code":"payload_too_large","message":"Request body too large",'
            b'"request_id":"' + rid.encode() + b'"}}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
