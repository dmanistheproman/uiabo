from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.account import router as account_router
from app.routers.analysis import router as analysis_router
from app.routers.link_safety import router as link_safety_router
from app.routers.portal import router as portal_router


app = FastAPI(
    title="uiabo API",
    version="0.1.0"
)

# The Expo web bundle (and the dev consoles) call the API directly from the
# browser. Local-only origins; the mobile apps use Bearer tokens, not cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


app.include_router(analysis_router)
app.include_router(link_safety_router)
app.include_router(account_router)
app.include_router(portal_router)


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
