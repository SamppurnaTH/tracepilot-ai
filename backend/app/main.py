from fastapi import FastAPI

app = FastAPI(title="TracePilot AI")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
