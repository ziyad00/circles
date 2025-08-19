from typing import Union
from fastapi import FastAPI
from .routers.health import router as health_router
from .routers.auth import router as auth_router
from .routers.places import router as places_router
from .database import create_tables

app = FastAPI(title="Circles")

# Include routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(places_router)


@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup"""
    await create_tables()


@app.get("/")
async def root():
    return {"hello": "world"}
