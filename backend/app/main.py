from fastapi import FastAPI

from app.routers.analysis import router as analysis_router


app = FastAPI(
    title="uiabo API",
    version="0.1.0"
)


app.include_router(analysis_router)


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