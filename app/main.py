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
from .routers.users import router as users_router
from .routers.support import router as support_router
from .database import create_tables
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
import uuid
from fastapi import Request
from fastapi.responses import JSONResponse


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
app.include_router(users_router)
app.include_router(support_router)

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


@app.middleware("http")
async def add_request_id_and_errors(request: Request, call_next):
    request_id = str(uuid.uuid4())
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error",
                     "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )


@app.get("/")
async def root():
    return {"hello": "world"}
