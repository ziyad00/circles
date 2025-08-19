from typing import Union
from fastapi import FastAPI
from .routers.health import router as health_router
from .routers.auth import router as auth_router
from .routers.places import router as places_router
from .database import create_tables
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Circles", lifespan=lifespan)

# Include routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(places_router)


@app.get("/")
async def root():
    return {"hello": "world"}
