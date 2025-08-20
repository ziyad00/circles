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
from .routers.dms_ws import router as dms_ws_router
from .routers.checkins import router as checkins_router
from .routers.activity import router as activity_router
from .routers.onboarding import router as onboarding_router
from .database import create_tables
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
import uuid
from fastapi import Request
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
import logging
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST


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
app.include_router(dms_ws_router)
app.include_router(checkins_router)
app.include_router(activity_router)
app.include_router(onboarding_router)

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

# Prometheus metrics
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", [
                        "method", "route", "status"])
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5)
)


@app.middleware("http")
async def add_request_id_and_errors(request: Request, call_next):
    request_id = str(uuid.uuid4())
    user_id = request.headers.get("x-user-id") or "anon"
    # Lightweight JSON log (sample all in debug, sample 10% in prod)
    import random
    if settings.debug or random.random() < 0.1:
        logging.info({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "rid": request_id,
            "user_id": user_id,
        })
    try:
        import time
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        REQUEST_LATENCY.observe(elapsed)
        route = getattr(request.scope.get("route"), "path", request.url.path)
        REQUEST_COUNT.labels(method=request.method,
                             route=route, status=response.status_code).inc()
        response.headers["X-Request-ID"] = request_id
        return response
    except RequestValidationError as e:
        logging.exception(f"Validation error rid={request_id}")
        route = getattr(request.scope.get("route"), "path", request.url.path)
        REQUEST_COUNT.labels(method=request.method,
                             route=route, status=422).inc()
        body = {
            "error": {
                "code": "validation_error",
                "message": "Validation error",
                "details": e.errors(),
            },
            "request_id": request_id,
        }
        return JSONResponse(status_code=422, content=body, headers={"X-Request-ID": request_id})
    except HTTPException as e:
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            429: "too_many_requests",
        }
        code = code_map.get(e.status_code, "error")
        route = getattr(request.scope.get("route"), "path", request.url.path)
        REQUEST_COUNT.labels(method=request.method,
                             route=route, status=e.status_code).inc()
        body = {
            "error": {
                "code": code,
                "message": e.detail if isinstance(e.detail, str) else str(e.detail),
            },
            "request_id": request_id,
        }
        return JSONResponse(status_code=e.status_code, content=body, headers={"X-Request-ID": request_id})
    except Exception as e:
        logging.exception(f"Unhandled error rid={request_id}")
        route = getattr(request.scope.get("route"), "path", request.url.path)
        REQUEST_COUNT.labels(method=request.method,
                             route=route, status=500).inc()
        body = {
            "error": {
                "code": "internal_server_error",
                "message": "Internal Server Error",
            },
            "request_id": request_id,
        }
        return JSONResponse(status_code=500, content=body, headers={"X-Request-ID": request_id})


@app.get("/")
async def root():
    return {"hello": "world"}


@app.get("/metrics")
async def metrics(request: Request):
    # In dev/debug mode, expose metrics without auth
    if not settings.debug:
        token = request.headers.get("X-Metrics-Token")
        if not settings.metrics_token or token != settings.metrics_token:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    data = generate_latest()
    return PlainTextResponse(content=data, media_type=CONTENT_TYPE_LATEST)
