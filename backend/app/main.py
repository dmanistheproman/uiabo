from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.account import router as account_router
from app.routers.analysis import router as analysis_router
from app.routers.link_safety import router as link_safety_router


app = FastAPI(
    title="uiabo API",
    version="0.1.0"
)

# The Expo web client (browser) is served from a different origin and sends a
# CORS preflight (OPTIONS) before PUT/POST requests; native clients are unaffected.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


app.include_router(analysis_router)
app.include_router(link_safety_router)
app.include_router(account_router)


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
