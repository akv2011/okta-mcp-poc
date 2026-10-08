from fastapi import FastAPI

app = FastAPI(title="hello-world backend")


@app.get("/hello")
def hello(name: str = "world"):
    return {"message": f"hello {name}"}


@app.get("/stats")
def stats():
    return {"requests_today": 42, "queue_depth": 3}
