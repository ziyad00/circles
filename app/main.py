from typing import Union
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routers.health import router as health_router
from .routers.auth import router as auth_router
from .routers.places import router as places_router
from .routers.dms import router as dms_router
from .routers.follow import router as follow_router
from .routers.users import router as users_router
from .routers.dms_ws import router as dms_ws_router
from .routers.onboarding import router as onboarding_router
from .routers.collections import router as collections_router
from .routers.checkins_original import router as checkins_router
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

# Configure logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()

    # Auto-seed Saudi cities data if needed
    # TODO: Temporarily disable auto-seeding to fix save errors
    # try:
    #     from .services.auto_seeder_service import auto_seeder_service
    #     from .database import get_db

    #     async for db in get_db():
    #         seeding_result = await auto_seeder_service.auto_seed_if_needed(db)

    #         if seeding_result["status"] == "completed":
    #             logger.info(
    #                 f"Auto-seeding completed! Added {seeding_result['total_places_added']} places")
    #         elif seeding_result["status"] == "skipped":
    #             logger.info(
    #                 f"Auto-seeding skipped: {seeding_result['reason']}")
    #         else:
    #             logger.warning(
    #                 f"Auto-seeding failed: {seeding_result.get('error', 'Unknown error')}")

    #         break  # Only run once

    # except Exception as e:
    #     logger.error(f"Auto-seeding error: {e}")

    yield

    # Shutdown WebSocket connection manager
    try:
        from .routers.dms_ws import manager
        await manager.shutdown()
    except Exception as e:
        logger.error(f"Error shutting down WebSocket manager: {e}")


app = FastAPI(
    title="Circles - Social Location App",
    description="""
# Circles API Documentation

Circles is a social location-based application that allows users to discover places, check-in, share experiences, and connect with followers.

## 🚀 Quick Start

1. **Authentication**: Use OTP-based authentication with phone only
2. **Places**: Discover and explore places around you
3. **Check-ins**: Share your location and experiences
4. **Social Features**: Follow users, send DMs, and view activity feeds
5. **Collections**: Organize your check-ins into themed collections

## 🔐 Authentication

All authenticated endpoints require a Bearer token obtained from:
- `POST /onboarding/verify-otp` (phone-based)

Include the token in the Authorization header: `Authorization: Bearer <your_token>`

## 📍 Core Features

### Places & Check-ins
- **Discover Places**: Search, filter, and explore places
- **Check-in**: Share your location with photos and notes
- **Trending**: See what's popular in your area
- **Recommendations**: Personalized place suggestions

### Social Features
- **Follow System**: Follow users to see their activity
- **Direct Messages**: Private conversations with typing indicators
- **Activity Feed**: Real-time updates from followed users
- **Collections**: Organize check-ins into themed groups

### Privacy & Settings
- **Visibility Controls**: Public, followers-only, or private content
- **DM Privacy**: Control who can message you
- **Notification Preferences**: Customize your notification settings

## 🛠️ Development

### Rate Limits
- OTP Requests: 3 per minute per IP
- OTP Verification: 5 per minute per IP
- DM Requests: 5 per minute per user
- DM Messages: 20 per minute per user

### File Uploads
- Photos: JPEG, PNG, WebP (max 10MB)
- Avatars: JPEG, PNG (max 5MB)
- Local storage used for development

### Proximity Enforcement
- Check-ins require user to be within 500m of place (configurable)
- Can be disabled for development with `APP_CHECKIN_ENFORCE_PROXIMITY=false`

## 📱 Client Integration

### Real-time Features
- WebSocket connections for live DMs and notifications
- Typing indicators and presence updates
- Real-time activity feed updates

### Pagination
Most list endpoints support pagination with `limit` and `offset` parameters.

### Error Handling
All endpoints return consistent error responses with descriptive messages.

## 🔗 External Resources

- **API Documentation**: This Swagger UI
- **WebSocket Documentation**: See `/dms/ws` endpoint
- **Health Check**: `/health` for service status
- **Metrics**: `/metrics` for monitoring (protected in production)
""",
    version="1.0.0",
    contact={
        "name": "Circles API Support",
        "email": "support@circles.app",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan
)

# Include routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(places_router)
app.include_router(dms_router)
app.include_router(follow_router)
app.include_router(users_router)
app.include_router(dms_ws_router)
app.include_router(onboarding_router)
app.include_router(collections_router)
app.include_router(checkins_router)

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
