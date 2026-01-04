from fastapi import FastAPI
from fastapi import Request


app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/__whoami")
def whoami():
    return {
        "file": __file__,
        "app_id": id(app)
    }
