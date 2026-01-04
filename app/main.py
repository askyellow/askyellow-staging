from fastapi import FastAPI
from fastapi import Request


app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ask")
async def ask(request: Request):
    data = await request.json()
    return {
        "answer": "Ask endpoint is alive 🎉",
        "debug": data
    }
