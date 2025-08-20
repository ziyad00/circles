from typing import Union
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routers.health import router as health_router
from .routers.auth import router as auth_router
from .routers.places import router as places_router
from .routers.dms import router as dms_router
from .routers.follow import router as follow_router
from .routers.collections import router as collections_router
from .routers.settings import router as settings_router
from .database import create_tables
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Circles", lifespan=lifespan)

# Include routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(places_router)
app.include_router(dms_router)
app.include_router(follow_router)
app.include_router(collections_router)
app.include_router(settings_router)

# Serve uploaded media
app.mount("/media", StaticFiles(directory="media"), name="media")

# CORS for UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"hello": "world"}
