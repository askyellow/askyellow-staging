from fastapi import FastAPI
import uvicorn

app = FastAPI()


@app.get("/")
def root():
    return {"ok": True}


if __name__ == "__main__":
    print("➡️  Starting uvicorn manually...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
