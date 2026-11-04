import asyncio
import logging
from contextlib import asynccontextmanager
from app.accounts.deletion import get_deletion_service
from app.portal.audit import AuditMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.pipeline.shared.errors import PipelineError

from app.routers.account import router as account_router
from app.routers.admin import router as admin_router
from app.routers.analysis import router as analysis_router
from app.routers.link_safety import router as link_safety_router
from app.routers.ocr import router as ocr_router
from app.routers.portal import router as portal_router
from app.routers.deepfakeAI_analysis import router as deepfakeAI_analysis_router
from app.routers.image_context_analysis import router as image_context_analysis_router


async def _deletion_worker(app):
    while True:
        try:
            factory = app.dependency_overrides.get(get_deletion_service, get_deletion_service)
            await asyncio.to_thread(factory().run_pending)
        except Exception:
            logging.getLogger(__name__).warning("Account deletion worker will retry.")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_deletion_worker(app))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="uiabo API",
    version="0.1.0", lifespan=lifespan
)


@app.exception_handler(PipelineError)
async def pipeline_error_response(request: Request, error: PipelineError):
    """Keep dependency failures in the same safe envelope as in-route errors."""
    return JSONResponse(status_code=error.http_status, content={"detail": {
        "error_code": error.error_code,
        "message": error.message,
        "stage": error.stage,
        "retryable": error.retryable,
    }})

# The Expo web bundle (and the dev consoles) call the API directly from the
# browser. Local-only origins; the mobile apps use Bearer tokens, not cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


from app.analyses.upload_limit import ImageUploadLimit
app.add_middleware(ImageUploadLimit)
app.add_middleware(AuditMiddleware)

app.include_router(analysis_router)
app.include_router(link_safety_router)
app.include_router(ocr_router)
app.include_router(account_router)
app.include_router(admin_router)
app.include_router(portal_router)

app.include_router(deepfakeAI_analysis_router)
app.include_router(image_context_analysis_router)

@app.get("/")
def root():
    return {
        "message": "uiabo API"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }
