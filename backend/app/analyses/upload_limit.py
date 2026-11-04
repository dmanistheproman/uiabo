"""Reject oversized multipart bodies before Starlette spools an entire upload."""
from fastapi import HTTPException
from starlette.responses import JSONResponse


class ImageUploadLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in {"/analysis/image-context", "/analysis/deepfakeAI"}:
            return await self.app(scope, receive, send)
        limit = 11 * 1024 * 1024
        detail = {"error_code": "IMAGE_TOO_LARGE", "message": "Choose an image smaller than 10 MB."}
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length > limit:
            return await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, detail=detail)
            return message
        await self.app(scope, bounded_receive, send)
