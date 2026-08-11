from fastapi import FastAPI

app = FastAPI(
    title="uiabo API",
    version="0.1.0"
)


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