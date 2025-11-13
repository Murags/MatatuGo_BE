from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
from .database import alembic_manager
from .v1.router import router as v1_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        alembic_manager.run_migrations()
    except Exception as e:
        print(f"Error running migrations: {e}")
        raise e
    yield

app = FastAPI(root_path="/api", lifespan=lifespan)

origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
