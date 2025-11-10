from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager
from .database import alembic_manager
from .v1.router import router as v1_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # try:
    #     alembic_manager.run_migrations()
    # except Exception as e:
    #     print(f"Error running migrations: {e}")
    #     raise e
    print("Skipping migrations just for testing purposes")
    yield

app = FastAPI(root_path="/api", lifespan=lifespan)

app.include_router(v1_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
