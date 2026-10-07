from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.files import router as files_router
from app.db import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Geospatial File Measurement API", version="1.0.0", lifespan=lifespan)
app.include_router(files_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
