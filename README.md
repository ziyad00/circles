# Circles - OTP Auth + Places/Check-Ins API

A FastAPI application with OTP (One-Time Password) authentication and core Places/Check-Ins features, backed by PostgreSQL.

## Features

- OTP-based authentication (email)
- JWT issuance and authenticated endpoints
- Core Places: create, search (filters), trending
- Check-Ins with 24h visibility window and basic rate-limiting
- Saved places lists
- Follows (one-way) model; privacy for check-ins respects followers/private/public
- Direct Messages (DMs): requests, inbox, unread counts, mark-as-read, mute, block, typing, presence, heart/like
- Photos on Reviews (multipart upload), pluggable storage (local/S3)
- Multiple photos per Check-In
- Check-In Collections with per-collection visibility (public/friends/private)
- User privacy settings to control default check-in/collection visibility and DM privacy
- User Profiles (name, bio, avatar) and Interests
- Support tickets (create, list by user)
- PostgreSQL + Alembic migrations

## Setup

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- uv (Python package manager)

### Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd circles
   ```

2. **Install dependencies**

   ```bash
   uv sync
   ```

   Or Option A (pip with requirements.txt):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Start PostgreSQL database**

   ```bash
   docker-compose up -d postgres
   ```

4. **Run database migrations**

   ```bash
   uv run alembic upgrade heads
   ```

5. **Start the application**
   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

The API will be available at `http://localhost:8000`

## How to Run

### Notes

- The API may take 30–60 seconds to become ready on first boot.
- Auto-seeding for Saudi cities runs on startup (OSM Overpass). Configure failover endpoints via `APP_OVERPASS_ENDPOINTS` in `.env`.

### Method 1: Quick Start with Docker (Recommended)

The fastest way to get the Circles application running:

#### Prerequisites

- Docker and Docker Compose installed
- Git

#### Steps

1. **Clone and navigate to the project**

   ```bash
   git clone <repository-url>
   cd circles
   ```

2. **Start everything with Docker Compose**

   ```bash
   docker-compose up --build
   ```

   This will:

   - Start PostgreSQL database
   - Build and start the FastAPI application
   - Run database migrations automatically
   - Make the API available at `http://localhost:8000`

3. **Wait for startup** (about 30-60 seconds)

   ```bash
   # Check if the app is ready
   curl --max-time 10 http://localhost:8000/health
   ```

4. **Populate with sample data** (optional)

   ```bash
   docker exec circles_app uv run python scripts/populate_sample_data.py
   ```

5. **Access the application**
   - **API Documentation**: http://localhost:8000/docs (Swagger UI)
   - **Health Check**: http://localhost:8000/health
   - **Metrics**: http://localhost:8000/metrics (dev mode only)

#### Troubleshooting Docker

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs app

# Restart if needed
docker-compose restart app

# Clean restart (removes data)
docker-compose down -v
docker-compose up --build
```

##### Debugging: Verify database container

Use these to confirm PostgreSQL is up and reachable from the app:

```bash
# 1) List containers and status
docker-compose ps
```

Example output:

```
    Name                   Command               State           Ports
-----------------------------------------------------------------------------
circles_app        /bin/sh -c uv run alembic  ...   Up      0.0.0.0:8000->8000/tcp
circles_postgres   docker-entrypoint.sh postgres    Up      0.0.0.0:5432->5432/tcp
```

```bash
# 2) Show recent database logs
docker-compose logs postgres | tail -n 50
```

Example output:

```
postgres  | 2025-08-26 10:12:34.567 UTC [1] LOG:  database system is ready to accept connections
postgres  | 2025-08-26 10:12:36.890 UTC [35] LOG:  connection authorized: user=postgres database=postgres
postgres  | 2025-08-26 10:12:37.123 UTC [42] LOG:  listening on IPv4 address "0.0.0.0", port 5432
```

```bash
# 3) Exec into DB container to list databases
docker exec -it circles_postgres psql -U postgres -c "\l"
```

Example output (excerpt):

```
                                   List of databases
    Name    |  Owner   | Encoding |   Collate   |    Ctype    |   Access privileges
------------+----------+----------+-------------+-------------+-----------------------
 postgres   | postgres | UTF8     | en_US.utf8  | en_US.utf8  |
 template0  | postgres | UTF8     | en_US.utf8  | en_US.utf8  | =c/postgres          +
 template1  | postgres | UTF8     | en_US.utf8  | en_US.utf8  | =c/postgres          +
 circles    | postgres | UTF8     | en_US.utf8  | en_US.utf8  |
(4 rows)
```

```bash
# 4) From the app container, test connectivity to DB
docker exec -it circles_app bash -lc "pg_isready -h postgres -p 5432 -U postgres || true"
```

Example output:

```
postgres:5432 - accepting connections
```

```bash
# 5) From the app container, run a quick SQL via psql
docker exec -it circles_app bash -lc "psql 'postgresql://postgres:password@postgres:5432/postgres' -c 'SELECT 1;'"
```

Example output:

```
 ?column?
----------
        1
(1 row)
```

If the DB is healthy but the app still fails to connect, check the app container env:

```bash
docker exec circles_app env | grep APP_DATABASE_URL
```

Example output:

```
APP_DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/circles
```

Ensure the hostname is `postgres` (the service name), not `localhost`.

##### Debugging: Verify application container

```bash
# 1) Show app logs
docker-compose logs app | tail -n 100
```

Example output:

```
app  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
app  | INFO:     Application startup complete
app  | INFO:     Auto-seed: should_seed_data=True; starting Saudi cities seeding...
```

```bash
# 2) Check container health and port mapping
docker-compose ps app
```

Example output:

```
    Name         Command                State                Ports
--------------------------------------------------------------------------
circles_app   /bin/sh -c uv run ...     Up       0.0.0.0:8000->8000/tcp
```

```bash
# 3) Hit health endpoint from HOST with timeout
curl --max-time 10 -sS http://localhost:8000/health
```

Example output:

```
{"status":"ok"}
```

```bash
# 4) Hit health endpoint from INSIDE the app container
docker exec -it circles_app bash -lc "curl --max-time 10 -sS http://localhost:8000/health || true"
```

If this works inside but not outside, suspect a host firewall/VPN/proxy.

```bash
# 5) Check env & migrations inside app
docker exec circles_app env | egrep "APP_ENV|APP_DATABASE_URL|APP_OVERPASS_ENDPOINTS"
docker exec -it circles_app bash -lc "uv run alembic current -v | cat"
docker exec -it circles_app bash -lc "uv run alembic heads -v | cat"
```

Expected: `current` should point to the latest revision and match one of the `heads`.

If `Multiple head revisions` appears, the compose command must use `uv run alembic upgrade heads` (plural). Fix by ensuring compose config does so.

##### Networking checks and solutions

```bash
# Port conflicts
lsof -iTCP:8000 -sTCP:LISTEN | cat
lsof -iTCP:5432 -sTCP:LISTEN | cat
```

If another process is listening, stop it or change ports in compose.

```bash
# Curl hangs – try these flags
curl --max-time 10 --connect-timeout 3 --ipv4 --http1.1 --noproxy localhost http://localhost:8000/health
```

If CLI still hangs but browser works, check VPN/proxy/security tools. Disable for `localhost` or add split-tunneling. Also check env vars:

```bash
env | egrep "HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY"
```

Ensure `NO_PROXY` includes `localhost,127.0.0.1`.

##### Migrations: diagnose and fix

```bash
# Status
docker exec -it circles_app bash -lc "uv run alembic current | cat"
docker exec -it circles_app bash -lc "uv run alembic history --verbose | tail -n 20 | cat"

# Apply (inside container)
docker exec -it circles_app bash -lc "uv run alembic upgrade heads"
```

Common issues and solutions:

- Multiple heads: ensure compose uses `upgrade heads` and no stray files exist in `alembic/versions/`.
- Missing table (e.g., users): use a single comprehensive initial migration, then incremental ones in order.

##### PostGIS verification (optional)

```bash
docker exec -it circles_postgres psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS postgis; SELECT PostGIS_Version();"
```

Example output:

```
  postgis_version
-------------------
 3.4.0
(1 row)
```

If extension is unavailable, switch to a PostGIS image (e.g., `postgis/postgis`) or install it in the DB image.

##### FastAPI/OpenAPI quick checks

```bash
curl --max-time 10 -sS http://localhost:8000/openapi.json | jq '.info.title,.paths | length'
curl --max-time 10 -sS http://localhost:8000/docs >/dev/null && echo "Docs served"
```

##### Metrics endpoint

```bash
# If APP_METRICS_TOKEN is set to token 'secret', use:
curl --max-time 10 -sS -H "Authorization: Bearer secret" http://localhost:8000/metrics | head -n 5
```

Example output:

```
# HELP process_cpu_seconds_total Total user and system CPU time spent in seconds.
# TYPE process_cpu_seconds_total counter
```

If 403/401, confirm token, and in dev mode the endpoint may be open.

##### WebSockets (DMs)

Use a client like `wscat` or `websocat`:

```bash
wscat -c ws://localhost:8000/ws/dms?thread_id=<ID>&token=<JWT>
```

Expected: connection opens, messages echo per protocol. If disconnects occur, check app logs for timeouts and ensure `APP_WS_SEND_TIMEOUT_SECONDS` is adequate.

##### File uploads (avatar and check-in photos)

```bash
# Avatar upload (replace <JWT>)
curl --max-time 10 -sS -H "Authorization: Bearer <JWT>" \
  -F "file=@/path/to/image.jpg;type=image/jpeg" \
  http://localhost:8000/users/me/avatar
```

Expected: 200 JSON with avatar URL. If 400, check content-type/size and ensure `APP_AVATAR_MAX_MB` is sufficient.

```bash
# Check-in photo upload (replace <JWT>, <CHECKIN_ID>)
curl --max-time 10 -sS -H "Authorization: Bearer <JWT>" \
  -F "file=@/path/to/image.jpg;type=image/jpeg" \
  http://localhost:8000/places/check-ins/<CHECKIN_ID>/photo
```

If using S3, verify AWS credentials and bucket perms. For local storage, verify files appear under the configured media directory.

##### External data (Overpass & Foursquare)

```bash
# Check configured Overpass endpoints in app env
docker exec circles_app env | grep APP_OVERPASS_ENDPOINTS

# Observe Overpass attempts and failover in logs
docker-compose logs app | egrep -i "overpass|timeout|retry" | tail -n 50
```

If Overpass times out, confirm endpoints list contains multiple mirrors and `APP_OVERPASS_TIMEOUT_SECONDS` is reasonable.

For Foursquare, ensure `APP_FOURSQUARE_API_KEY` is set; without it, enrichment/discovery gracefully degrades but some calls may return fewer details.

##### Activity feed, support/admin quick checks

```bash
# Support ticket create (replace <JWT>)
curl --max-time 10 -sS -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"subject":"test","body":"hello"}' \
  http://localhost:8000/support/tickets
```

Expected: 200/201 with ticket payload. If 500, confirm payload matches schema (uses `message` internally).

##### Common issues and targeted fixes

- App up but health fails: check `APP_DATABASE_URL` host is `postgres`, not `localhost`; verify DB accepts connections with `pg_isready`.
- `curl` hangs: use the flags above; disable VPN/proxy for localhost; ensure `NO_PROXY` includes localhost.
- Migrations error: ensure only `001_initial_schema.py` + sequential follow-ups exist; run `upgrade heads`.
- PostGIS features slow/ignored: install PostGIS and create indexes; or rely on Haversine fallback with appropriate radius.
- S3 blocking loop: confirm thread offloading is enabled (it is by default via `asyncio.to_thread`).
- DM request blocked: verify block rules and privacy settings; logs will show recipient checks.

### Method 2: Local Development Setup

For local development without Docker:

#### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- uv package manager

#### Steps

Quick steps (TL;DR):

```bash
# 1) Ensure PostgreSQL is running and create the database
createdb circles            # macOS/Linux; or create via pgAdmin/psql on Windows

# 2) Copy env and set DB URL
cp .env.example .env
# Edit .env and set:
# APP_DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/circles

# 3) Install dependencies
uv sync                     # or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 4) Run database migrations (apply all heads)
uv run alembic upgrade heads

# 5) Start the app
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6) Test
curl --max-time 10 http://localhost:8000/health
```

Notes:

- `APP_DATABASE_URL` must use the async driver: `postgresql+asyncpg://...`
- Use `heads` (plural) for Alembic to apply all head revisions (not `head`).
- `uv sync` installs project dependencies; `uv run <cmd>` executes `<cmd>` inside the project's virtual environment.

1. **Install uv** (if not installed)

   ```bash
   # macOS
   brew install uv

   # Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Windows
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Install dependencies**

   ```bash
   uv sync
   ```

3. **Set up environment variables**

   ```bash
   cp .env.example .env
   ```

4. **Configure database connection**

   Edit `.env` file:

   ```bash
   # For local PostgreSQL
   APP_DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/circles

   # Or use Docker for database only
   APP_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/circles
   ```

5. **Start PostgreSQL**

   **Option A: Local PostgreSQL**

   ```bash
   # macOS with Homebrew
   brew install postgresql@15
   brew services start postgresql@15

   # Create database
   createdb circles
   ```

   **Option B: Docker PostgreSQL only**

   ```bash
   docker-compose up -d postgres
   ```

6. **Run migrations**

   ```bash
   uv run alembic upgrade heads
   ```

7. **Start the application**

   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

8. **Test the application**
   ```bash
   curl --max-time 10 http://localhost:8000/health
   ```

### Method 3: Production Setup

For production deployment:
PostGIS

#### Prerequisites

- Python 3.12+
- PostgreSQL 15+ with PostGIS extension
- uv package manager
- Reverse proxy (nginx, etc.)

#### Steps

1. **Install dependencies**

   ```bash
   uv sync --frozen
   ```

2. **Set up environment variables**

   ```bash
   cp .env.example .env
   # Edit with production values
   ```

3. **Configure production settings**

   ```bash
   # In .env file
   APP_DEBUG=false
   APP_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
   APP_OTP_SECRET_KEY=your-secure-secret-key
   APP_JWT_SECRET_KEY=your-secure-jwt-secret
   APP_STORAGE_BACKEND=s3  # or local
   APP_USE_POSTGIS=true
   ```

4. **Run migrations**

   ```bash
   uv run alembic upgrade heads
   ```

5. **Start with production server**
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

### Testing Your Setup

Once the application is running, test it:

```bash
# Health check (with timeout)
curl --max-time 10 http://localhost:8000/health

# Request OTP (with timeout)
curl --max-time 10 -X POST "http://localhost:8000/auth/request-otp" \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com"}'

# Check API docs
open http://localhost:8000/docs
```

### Common Issues and Solutions

#### Migration Issues (Most Common)

The project has some migration dependency issues. Here's how to fix them:

**Option 1: Fresh Start (Recommended)**

```bash
# Stop everything
docker-compose down -v

# Start fresh
docker-compose up --build
```

**Option 2: Manual Migration Fix**

```bash
# If you get "relation 'users' does not exist" error
# This means the migration order is wrong

# Reset the database
docker-compose down -v
docker volume rm circles_postgres_data

# Start PostgreSQL only
docker-compose up -d postgres

# Wait for PostgreSQL to be ready
sleep 10

# Run migrations with proper order
uv run alembic upgrade heads
```

#### Docker Issues

```bash
# Port already in use
docker-compose down
docker-compose up --build

# Migration errors
docker-compose down -v
docker-compose up --build

# Container not starting
docker-compose logs app

# Health check failing
# Wait 30-60 seconds for startup, then check:
curl --max-time 10 http://localhost:8000/health
```

#### Local Development Issues

```bash
# Database connection failed
# Check if PostgreSQL is running
brew services list | grep postgresql

# Migration errors
uv run alembic upgrade heads

# Port already in use
lsof -ti:8000 | xargs kill -9

# Environment variables not loaded
# Make sure .env file exists and has correct values
cat .env
```

#### Environment Variables

Make sure your `.env` file has the correct database URL:

```bash
# For Docker PostgreSQL
APP_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/circles

# For local PostgreSQL
APP_DATABASE_URL=postgresql+asyncpg://youruser:yourpass@localhost:5432/circles

# Required environment variables
APP_DEBUG=true
APP_OTP_SECRET_KEY=dev-secret-key-change-in-production
APP_JWT_SECRET_KEY=dev-jwt-secret-key-change-in-production
```

#### Testing Your Setup

```bash
# Test with timeouts to avoid hanging
curl --max-time 10 http://localhost:8000/health

# Test OTP request
curl --max-time 10 -X POST "http://localhost:8000/auth/request-otp" \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com"}'

# Check API docs
open http://localhost:8000/docs
```

### Testing the API

Once the application is running, you can:

1. **View API Documentation**

   - Open http://localhost:8000/docs in your browser
   - Interactive Swagger UI with all endpoints
   - **Complete API Documentation**: See `docs/swagger_api_documentation.txt` for comprehensive endpoint documentation

2. **Test endpoints with curl**

   ```bash
   # Health check
   curl http://localhost:8000/health

   # Request OTP
   curl -X POST "http://localhost:8000/auth/request-otp" \
        -H "Content-Type: application/json" \
        -d '{"email": "test@example.com"}'
   ```

3. **Use sample data**
   - Run the population script to get realistic test data
   - 20 users, 8 places, check-ins, messages, and more

### Stopping the Application

```bash
# Stop Docker containers
docker-compose down

# Stop local development server
# Press Ctrl+C in the terminal running uvicorn
```

## API Endpoints

### Authentication

- `POST /auth/request-otp` - Request an OTP code (rate limited: 3/min)
- `POST /auth/verify-otp` - Verify OTP code and authenticate (rate limited: 5/min)

### Health Check

### Rate Limiting

The API implements rate limiting to prevent abuse:

- **OTP Requests**: 3 requests per minute per IP
- **OTP Verification**: 5 attempts per minute per IP
- **DM Requests**: 5 requests per minute per user
- **DM Messages**: 20 messages per minute per user

Rate limited requests return HTTP 429 with a descriptive error message.

### Users

- GET `/users/{user_id}` – Public profile
- PUT `/users/me` – Update my profile (name, bio)
- POST `/users/me/avatar` – Upload avatar (multipart)
- GET `/users/{user_id}/check-ins?limit=&offset=` – User check-ins (visibility enforced)
- GET `/users/{user_id}/media?limit=&offset=` – User media (review + check-in photos)
- GET `/users/me/interests` – List my interests
- POST `/users/me/interests` – Add an interest { name }
- DELETE `/users/me/interests/{interest_id}` – Remove an interest

### Support

- POST `/support/tickets` – Create a support ticket { subject, body }
- GET `/support/tickets` – List my tickets

- `GET /health` - Health check endpoint

### Follows

- `POST /follow/{user_id}` - Follow a user
- `DELETE /follow/{user_id}` - Unfollow a user
- `GET /follow/followers?limit=&offset=` - List my followers
- `GET /follow/following?limit=&offset=` - List who I follow

## Usage

### 1. Request OTP

```bash
curl -X POST "http://localhost:8000/auth/request-otp" \
     -H "Content-Type: application/json" \
     -d '{"email": "user@example.com"}'
```

Response:

```json
{
  "message": "OTP code sent to user@example.com. For development: 123456",
  "expires_in_minutes": 10
}
```

### 2. Verify OTP (get JWT)

```bash
curl -X POST "http://localhost:8000/auth/verify-otp" \
     -H "Content-Type: application/json" \
     -d '{"email": "user@example.com", "otp_code": "123456"}'
```

Response (access_token is returned and used as Bearer token):

```json
{
  "message": "OTP verified successfully",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "phone": null,
    "is_verified": true,
    "created_at": "2024-01-01T12:00:00"
  },
  "access_token": "<JWT>"
}
```

Use the token:

```bash
TOKEN="<JWT>"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/auth/me
```

---

### Privacy & Visibility

Check-ins and collections have visibility:

- `public`: Visible to everyone
- `friends` (followers): Visible to users who follow the owner
- `private`: Visible only to the owner

#### User Privacy Settings

- GET `/settings/privacy`
- PUT `/settings/privacy`

Payload example:

```json
{
  "dm_privacy": "followers", // everyone | followers | no_one
  "checkins_default_visibility": "friends",
  "collections_default_visibility": "private"
}
```

### Direct Messages (DM)

- POST `/dms/requests` – Start a DM (subject to recipient `dm_privacy`, rate limited: 5/min)
- GET `/dms/requests` – Pending DM requests
- PUT `/dms/requests/{thread_id}` – Accept/Reject
- GET `/dms/inbox` – Accepted threads
- GET `/dms/threads/{thread_id}/messages` – List messages
- POST `/dms/threads/{thread_id}/messages` – Send message (rate limited: 20/min)
- POST `/dms/threads/{thread_id}/messages/{message_id}/heart` – Like/Unlike
- GET `/dms/unread-count` and `/dms/threads/{id}/unread-count`
- POST `/dms/threads/{id}/mark-read`
- PUT `/dms/threads/{id}/mute` and `/dms/threads/{id}/block`
- POST `/dms/threads/{id}/typing` and GET `/dms/threads/{id}/typing`
- GET `/dms/threads/{id}/presence`

---

### Places & Check-Ins

All new endpoints live under `/places`.

Common pagination format for list endpoints:

```json
{
  "items": [
    /* array of resources */
  ],
  "total": 123,
  "limit": 20,
  "offset": 0
}
```

#### Create Place

POST `/places/`

```bash
curl -X POST http://localhost:8000/places/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Blue Bottle Coffee",
    "city": "San Francisco",
    "neighborhood": "SoMa",
    "categories": ["coffee","cafe"],
    "rating": 4.5,
    "latitude": 37.781,
    "longitude": -122.404
  }'
```

#### Get Place Details

GET `/places/{id}` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/places/1
```

Returns detailed place information including:

- Place details (name, address, coordinates, etc.)
- Statistics (average rating, review count, active check-ins)
- Current check-ins count (last 24h)
- Total check-ins ever
- Recent reviews count (last 30 days)
- Photos count
- User-specific data (is checked in, is saved)

#### Get Place Statistics

GET `/places/{id}/stats`

```bash
curl http://localhost:8000/places/1/stats
```

Returns place statistics:

- Average rating
- Total reviews count
- Active check-ins (last 24h)

#### Who's Here Now

GET `/places/{id}/whos-here` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/places/1/whos-here?limit=20&offset=0'
```

Returns paginated list of users currently checked in (last 24h), respecting privacy settings.

#### Who's Here Count

GET `/places/{id}/whos-here-count` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/places/1/whos-here-count
```

Returns count of people currently checked in.

#### Place Photos Gallery

GET `/places/{id}/photos`

```bash
curl 'http://localhost:8000/places/1/photos?limit=20&offset=0'
```

Returns paginated list of photos from reviews for this place.

#### Place Reviews

GET `/places/{id}/reviews`

```bash
curl 'http://localhost:8000/places/1/reviews?limit=20&offset=0'
```

Returns paginated list of reviews for this place.

#### Search Places (paginated)

GET `/places/search?query=&city=&neighborhood=&category=&rating_min=&limit=20&offset=0`

```bash
curl 'http://localhost:8000/places/search?city=San%20Francisco&limit=10&offset=0'
```

Returns `{ items, total, limit, offset }` with `items` as `PlaceResponse[]`.

#### Advanced Search

POST `/places/search/advanced`

```bash
curl -X POST "http://localhost:8000/places/search/advanced" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "coffee",
    "city": "San Francisco",
    "categories": ["coffee", "cafe"],
    "rating_min": 4.0,
    "rating_max": 5.0,
    "has_recent_checkins": true,
    "has_reviews": true,
    "has_photos": true,
    "latitude": 37.7749,
    "longitude": -122.4194,
    "radius_km": 5.0,
    "sort_by": "rating",
    "sort_order": "desc",
    "limit": 20,
    "offset": 0
  }'
```

Advanced search with multiple filters:

- **Text search**: Search in place names
- **Location filters**: City, neighborhood
- **Category filters**: Multiple categories support
- **Rating filters**: Min/max rating range
- **Activity filters**: Has recent check-ins, reviews, photos
- **Distance search**: Radius-based search with coordinates
- **Sorting**: By name, rating, created_at, checkins, recent_checkins
- **Pagination**: Limit and offset

#### Quick Search

GET `/places/search/quick?q=&limit=20&offset=0`

```bash
curl 'http://localhost:8000/places/search/quick?q=coffee&limit=10'
```

Quick search across multiple fields (name, city, neighborhood, categories).

#### Search Suggestions

GET `/places/search/suggestions?query=&limit=10`

```bash
curl 'http://localhost:8000/places/search/suggestions?query=san&limit=5'
```

Returns autocomplete suggestions for cities, neighborhoods, and categories.

#### External Suggestions (public)

GET `/places/external/suggestions?query=&lat=&lon=&limit=10`

```bash
curl 'http://localhost:8000/places/external/suggestions?query=cafe&lat=24.7&lon=46.7&limit=5'
```

Returns lightweight suggestions sourced from OSM; when coordinates are passed, results are bounded to the area.

#### Filter Options

GET `/places/search/filter-options`

```bash
curl 'http://localhost:8000/places/search/filter-options'
```

Returns available filter options with counts:

- Cities with place counts
- Neighborhoods with place counts
- Categories with place counts
- Rating range (min, max, average)

#### Trending Places (public, paginated)

GET `/places/trending?time_window=24h&limit=10&offset=0`

```bash
curl 'http://localhost:8000/places/trending?time_window=24h&limit=10'
```

Also available: global trending (no auth) – `GET /places/trending/global?limit=10&offset=0`.

#### Create Check-in

POST `/places/check-ins` (authenticated)

```bash
curl -X POST "http://localhost:8000/places/check-ins" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": 1,
    "note": "Great coffee!",
    "latitude": 24.7136,
    "longitude": 46.6753,
    "visibility": "public"
  }'
```

**Request Body:**

```json
{
  "place_id": 1,
  "note": "Great coffee!",
  "latitude": 24.7136,
  "longitude": 46.6753,
  "visibility": "public"
}
```

**Response:**

```json
{
  "id": 1,
  "user_id": 1,
  "place_id": 1,
  "note": "Great coffee!",
  "visibility": "public",
  "created_at": "2024-01-01T12:00:00Z",
  "expires_at": "2024-01-02T12:00:00Z",
  "photo_url": null,
  "photo_urls": []
}
```

**Features:**

- **Proximity Enforcement**: Users must be within 500m of the place to check in
- **Location Validation**: Requires current latitude/longitude coordinates
- **Rate Limiting**: 5-minute cooldown between check-ins to the same place
- **Visibility Control**: Public, followers, or private check-ins
- **Automatic Expiration**: Check-ins expire after 24 hours
- **Activity Integration**: Creates activity feed entries

**Proximity Enforcement:**

- **Default Distance**: 500 meters maximum distance
- **Configurable**: Set via `APP_CHECKIN_MAX_DISTANCE_METERS` environment variable
- **Disable Feature**: Set `APP_CHECKIN_ENFORCE_PROXIMITY=false` to disable
- **Haversine Calculation**: Uses great-circle distance formula
- **Error Messages**: Clear feedback when outside allowed range

**Error Responses:**

```json
{
  "detail": "You must be within 500 meters of Test Cafe to check in"
}
```

```json
{
  "detail": "Missing current location: latitude and longitude are required"
}
```

```json
{
  "detail": "Place coordinates missing; cannot verify proximity"
}
```

#### Save Place (auth)

POST `/places/saved`

```bash
curl -X POST http://localhost:8000/places/saved \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"place_id":1, "list_name":"Favorites"}'
```

#### My Saved Places (paginated, auth)

GET `/places/saved/me?limit=20&offset=0`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/places/saved/me?limit=10&offset=0'
```

#### Unsave Place (auth)

DELETE `/places/saved/{place_id}`

```bash
curl -X DELETE http://localhost:8000/places/saved/1 \
  -H "Authorization: Bearer $TOKEN" -i
```

#### My Check-ins (paginated, auth)

GET `/places/me/check-ins?limit=20&offset=0`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/places/me/check-ins?limit=10&offset=0'
```

Returns `{ items: CheckInResponse[], total, limit, offset }` ordered by newest first.

#### Reviews

- Create review (auth): POST `/places/{place_id}/reviews`

```bash
curl -X POST http://localhost:8000/places/1/reviews \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"rating":4.5, "text":"Great spot!"}'
```

- List reviews (paginated): GET `/places/{place_id}/reviews?limit=20&offset=0`

```bash
curl 'http://localhost:8000/places/1/reviews?limit=10&offset=0'
```

Returns `{ items: ReviewResponse[], total, limit, offset }` ordered by newest first.

- Delete my review (auth): DELETE `/places/{place_id}/reviews/me`

```bash
curl -X DELETE http://localhost:8000/places/1/reviews/me \
  -H "Authorization: Bearer $TOKEN" -i
```

- My reviews (paginated, auth): GET `/places/me/reviews?limit=&offset=`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/places/me/reviews?limit=10&offset=0'
```

Returns `{ items: ReviewResponse[], total, limit, offset }`.

#### Place Stats

GET `/places/{place_id}/stats`

```bash
curl 'http://localhost:8000/places/1/stats'
```

Returns:

```json
{
  "place_id": 1,
  "average_rating": 4.3,
  "reviews_count": 12,
  "active_checkins": 3
}
```

### Nearby Places

GET `/places/nearby?lat=&lng=&radius_m=1000&limit=20&offset=0`

```bash
curl 'http://localhost:8000/places/nearby?lat=37.78&lng=-122.41&radius_m=1500&limit=10'
```

Returns places within radius, ordered by distance (Haversine).

### Who's Here Count

GET `/places/{place_id}/whos-here/count`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/places/1/whos-here/count'
```

Returns `{ "count": number }` of visible, non-expired check-ins (respects privacy settings).

### Check-in Delete

### Photos

- Upload review photo: POST `/places/reviews/{review_id}/photos` (multipart)
- List place photos (from reviews): GET `/places/{place_id}/photos`
- Delete review photo: DELETE `/places/reviews/{review_id}/photos/{photo_id}`
- Upload check-in photo: POST `/places/check-ins/{check_in_id}/photo` (repeat to add multiple)
- List check-in photos: GET `/places/check-ins/{check_in_id}/photos`
- Delete one/all check-in photos: DELETE `/places/check-ins/{check_in_id}/photos/{photo_id}` and `/places/check-ins/{check_in_id}/photo`

### Collections

- Create: POST `/collections` { name, visibility? }
- List: GET `/collections`
- Rename/update visibility: PATCH `/collections/{collection_id}` { name, visibility? }
- Delete: DELETE `/collections/{collection_id}`
- Add check-in: POST `/collections/{collection_id}/items/{check_in_id}`
- List items: GET `/collections/{collection_id}/items` (respects collection visibility)
- Remove item: DELETE `/collections/{collection_id}/items/{item_id}`

DELETE `/places/check-ins/{check_in_id}` (auth)

```bash
curl -X DELETE http://localhost:8000/places/check-ins/123 \
  -H "Authorization: Bearer $TOKEN" -i
```

#### Get My Check-ins

GET `/places/me/check-ins?limit=20&offset=0` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/places/me/check-ins"
```

Returns `{ items, total, limit, offset }` with `items` as `CheckInResponse[]`.

#### Get Check-in Details

GET `/check-ins/{check_in_id}` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/check-ins/42"
```

Returns detailed check-in information including:

- Check-in details (note, visibility, created_at)
- User information (name, avatar)
- Place information (name, address, city, neighborhood, categories, rating)
- Photo URLs
- Like and comment counts
- User-specific data (is_liked_by_current_user, can_edit, can_delete)

#### Get Check-in Statistics

GET `/check-ins/{check_in_id}/stats` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/check-ins/42/stats"
```

Returns check-in statistics (likes_count, comments_count, views_count).

#### Get Check-in Comments

GET `/check-ins/{check_in_id}/comments?limit=20&offset=0` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/check-ins/42/comments"
```

Returns paginated list of comments for a check-in.

#### Add Check-in Comment

POST `/check-ins/{check_in_id}/comments` (authenticated)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Great place! Love the coffee here."}' \
  "http://localhost:8000/check-ins/42/comments"
```

Add a comment to a check-in.

#### Delete Check-in Comment

DELETE `/check-ins/{check_in_id}/comments/{comment_id}` (authenticated)

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/check-ins/42/comments/1"
```

Delete a comment (only comment author or check-in author can delete).

#### Get Check-in Likes

GET `/check-ins/{check_in_id}/likes?limit=20&offset=0` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/check-ins/42/likes"
```

Returns paginated list of users who liked the check-in.

#### Like Check-in

POST `/check-ins/{check_in_id}/like` (authenticated)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/check-ins/42/like"
```

Like a check-in.

#### Unlike Check-in

DELETE `/check-ins/{check_in_id}/like` (authenticated)

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/check-ins/42/like"
```

Unlike a check-in.

## Onboarding Flow

The onboarding flow provides a streamlined user registration and setup process using phone number authentication and OTP verification.

### Onboarding Flow Overview

1. **Phone OTP Request**: User enters phone number to receive OTP
2. **OTP Verification**: User verifies phone number with 6-digit OTP
3. **Profile Setup**: User completes profile with name, username, and interests
4. **Onboarding Complete**: User is ready to use the app

### Onboarding Endpoints

#### Request Phone OTP

POST `/onboarding/request-otp` (public)

```bash
curl -X POST "http://localhost:8000/onboarding/request-otp" \
  -H "Content-Type: application/json" \
  -d '{"phone": "+1234567890"}'
```

**Request Body:**

```json
{
  "phone": "+1234567890"
}
```

**Response:**

```json
{
  "message": "OTP sent successfully",
  "otp": "123456",
  "is_new_user": true
}
```

**Features:**

- Phone number validation (international format)
- Rate limiting (5 minutes between requests)
- 6-digit OTP generation
- 10-minute OTP expiration
- New user detection

#### Verify Phone OTP

POST `/onboarding/verify-otp` (public)

```bash
curl -X POST "http://localhost:8000/onboarding/verify-otp" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+1234567890",
    "otp_code": "123456"
  }'
```

**Request Body:**

```json
{
  "phone": "+1234567890",
  "otp_code": "123456"
}
```

**Response for New User:**

```json
{
  "message": "OTP verified. Please complete your profile.",
  "user": {
    "id": 18,
    "phone": "+1234567890",
    "email": null,
    "username": null,
    "first_name": null,
    "last_name": null,
    "is_verified": true,
    "is_onboarded": false
  },
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "is_new_user": true
}
```

**Response for Existing User:**

```json
{
  "message": "Login successful",
  "user": {
    "id": 18,
    "phone": "+1234567890",
    "email": "user@example.com",
    "username": "john_doe",
    "first_name": "John",
    "last_name": "Doe",
    "is_verified": true,
    "is_onboarded": true
  },
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "is_new_user": false
}
```

#### Check Username Availability

POST `/onboarding/check-username` (public)

```bash
curl -X POST "http://localhost:8000/onboarding/check-username" \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe"}'
```

**Request Body:**

```json
{
  "username": "john_doe"
}
```

**Response:**

```json
{
  "available": true,
  "message": "Username is available"
}
```

**Username Requirements:**

- 3-30 characters long
- Alphanumeric and underscores only
- Must be unique

#### Complete User Setup

POST `/onboarding/complete-setup` (authenticated)

```bash
curl -X POST "http://localhost:8000/onboarding/complete-setup" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "username": "john_doe",
    "interests": ["coffee", "restaurants", "travel"]
  }'
```

**Request Body:**

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "username": "john_doe",
  "interests": ["coffee", "restaurants", "travel"]
}
```

**Response:**

```json
{
  "message": "Profile setup completed successfully",
  "user": {
    "id": 18,
    "phone": "+1234567890",
    "email": null,
    "username": "john_doe",
    "first_name": "John",
    "last_name": "Doe",
    "name": "John Doe",
    "is_verified": true,
    "is_onboarded": true
  },
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "is_new_user": false
}
```

#### Get Onboarding Status

GET `/onboarding/status` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/onboarding/status"
```

**Response:**

```json
{
  "user": {
    "id": 18,
    "phone": "+1234567890",
    "email": null,
    "username": "john_doe",
    "first_name": "John",
    "last_name": "Doe",
    "name": "John Doe",
    "is_verified": true,
    "is_onboarded": true,
    "interests": ["coffee", "restaurants", "travel"]
  },
  "onboarding_complete": true
}
```

### Onboarding Flow Features

#### 1. **Phone Number Authentication**

- International phone number format support
- Phone number validation
- OTP-based verification
- Secure token generation

#### 2. **User Profile Setup**

- First and last name collection
- Unique username selection
- Interest selection (1-10 interests)
- Profile completion tracking

#### 3. **Security Features**

- Rate limiting for OTP requests
- OTP expiration (10 minutes)
- One-time use OTP codes
- JWT token authentication

#### 4. **User Experience**

- New vs existing user detection
- Real-time username availability check
- Clear onboarding status tracking
- Seamless profile completion

#### 5. **Data Validation**

- Phone number format validation
- Username format validation
- Interest count limits
- Required field validation

### Onboarding Flow Steps

#### Step 1: Phone OTP Request

1. User enters phone number
2. System validates phone format
3. System checks rate limiting
4. System generates and sends OTP
5. System returns OTP (development only)

#### Step 2: OTP Verification

1. User enters 6-digit OTP
2. System validates OTP
3. System checks if user exists
4. System creates new user or returns existing user
5. System generates authentication token

#### Step 3: Profile Setup (New Users)

1. User enters first and last name
2. User selects unique username
3. User selects interests (1-10)
4. System validates all inputs
5. System saves profile data
6. System marks onboarding as complete

#### Step 4: Onboarding Complete

1. User receives confirmation
2. User can access all app features
3. User profile is fully set up
4. User interests are saved

### Phone Number Requirements

#### Format

- International format required
- Must start with `+`
- 10-15 digits after `+`
- Examples: `+1234567890`, `+44123456789`

#### Validation

```javascript
// Phone number validation regex
/^\+\d{10,15}$/;
```

### Username Requirements

#### Format

- 3-30 characters long
- Alphanumeric and underscores only
- Must be unique across all users
- Case-sensitive

#### Validation

```javascript
// Username validation regex
/^[a-zA-Z0-9_]{3,30}$/;
```

### Interest Selection

#### Requirements

- 1-10 interests maximum
- Each interest trimmed of whitespace
- Duplicate interests ignored
- Interests stored as separate records

#### Example Interests

- Coffee
- Restaurants
- Travel
- Music
- Sports
- Technology
- Art
- Food
- Photography
- Fitness

### Onboarding Flow Benefits

#### 1. **Simplified Registration**

- No email required initially
- Quick phone verification
- Minimal friction

#### 2. **Secure Authentication**

- OTP-based verification
- Rate limiting protection
- Secure token generation

#### 3. **Complete Profile Setup**

- Structured data collection
- Interest-based personalization
- Username uniqueness

#### 4. **User Experience**

- Clear progress indication
- Real-time validation
- Seamless completion

#### 5. **Data Quality**

- Validated phone numbers
- Unique usernames
- Structured interests

### Integration with Other Features

#### 1. **Activity Feed**

- Interests used for content recommendations
- Personalized activity suggestions

#### 2. **User Profiles**

- Username used in profile URLs
- Interests displayed on profiles

#### 3. **Search and Discovery**

- Interests used for place recommendations
- Personalized search results

#### 4. **Social Features**

- Username used in mentions
- Interests for user matching

### Development vs Production

#### Development Mode

- OTP returned in response
- No actual SMS sending
- Faster testing

#### Production Mode

- OTP sent via SMS service
- OTP not returned in response
- Real SMS integration required

### Error Handling

#### Common Errors

- Invalid phone number format
- Rate limit exceeded
- Invalid or expired OTP
- Username already taken
- Invalid username format
- Too many interests

#### Error Responses

```json
{
  "detail": "Invalid phone number format. Please use international format (e.g., +1234567890)"
}
```

### Security Considerations

#### 1. **Rate Limiting**

- 5-minute cooldown between OTP requests
- Prevents OTP spam

#### 2. **OTP Security**

- 10-minute expiration
- One-time use only
- 6-digit random generation

#### 3. **Token Security**

- JWT-based authentication
- User ID and phone in token
- Secure token generation

#### 4. **Data Validation**

- Input sanitization
- Format validation
- Uniqueness checks

## Activity Feed

The Activity Feed shows recent activities from users you follow, providing a social timeline of check-ins, likes, comments, follows, reviews, and collections.

### Activity Feed Endpoints

#### Get Activity Feed

GET `/activity/feed?limit=20&offset=0&activity_types=checkin,like&since=2025-08-20T00:00:00Z` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/activity/feed"
```

Returns activities from users you follow, including:

- Check-ins
- Likes on check-ins
- Comments on check-ins
- Follow actions
- Reviews
- Collection creations

**Query Parameters:**

- `limit`: Number of activities to return (1-100, default: 20)
- `offset`: Number of activities to skip (default: 0)
- `activity_types`: Comma-separated list of activity types to filter
- `since`: Show activities since this timestamp
- `until`: Show activities until this timestamp

#### Get Filtered Activity Feed

POST `/activity/feed/filtered` (authenticated)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "activity_types": ["checkin", "like"],
    "user_ids": [2, 3],
    "since": "2025-08-20T00:00:00Z",
    "limit": 20,
    "offset": 0
  }' \
  "http://localhost:8000/activity/feed/filtered"
```

Advanced filtering with multiple criteria.

#### Get My Activities

GET `/activity/my-activities?limit=20&offset=0` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/activity/my-activities"
```

Returns your own activities.

#### Get User Activities

GET `/activity/user/{user_id}/activities?limit=20&offset=0` (authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/activity/user/2/activities"
```

Returns activities for a specific user (if you follow them or it's your own profile).

### Activity Types

#### Check-in Activity

```json
{
  "id": 1,
  "user_id": 2,
  "user_name": "John Doe",
  "user_avatar_url": "https://example.com/avatar.jpg",
  "activity_type": "checkin",
  "activity_data": {
    "checkin_id": 42,
    "place_name": "Coffee Shop",
    "note": "Great coffee here!"
  },
  "created_at": "2025-08-20T10:30:00Z"
}
```

#### Like Activity

```json
{
  "id": 2,
  "user_id": 3,
  "user_name": "Jane Smith",
  "user_avatar_url": "https://example.com/avatar2.jpg",
  "activity_type": "like",
  "activity_data": {
    "checkin_id": 42,
    "checkin_user_id": 2,
    "checkin_note": "Great coffee here!"
  },
  "created_at": "2025-08-20T10:35:00Z"
}
```

#### Comment Activity

```json
{
  "id": 3,
  "user_id": 4,
  "user_name": "Bob Wilson",
  "user_avatar_url": "https://example.com/avatar3.jpg",
  "activity_type": "comment",
  "activity_data": {
    "comment_id": 15,
    "checkin_id": 42,
    "checkin_user_id": 2,
    "comment_content": "I love this place too!"
  },
  "created_at": "2025-08-20T10:40:00Z"
}
```

#### Follow Activity

```json
{
  "id": 4,
  "user_id": 5,
  "user_name": "Alice Brown",
  "user_avatar_url": "https://example.com/avatar4.jpg",
  "activity_type": "follow",
  "activity_data": {
    "followee_id": 2,
    "followee_name": "John Doe"
  },
  "created_at": "2025-08-20T10:45:00Z"
}
```

#### Review Activity

```json
{
  "id": 5,
  "user_id": 2,
  "user_name": "John Doe",
  "user_avatar_url": "https://example.com/avatar.jpg",
  "activity_type": "review",
  "activity_data": {
    "review_id": 8,
    "place_name": "Coffee Shop",
    "rating": 4.5,
    "review_text": "Excellent coffee and atmosphere!"
  },
  "created_at": "2025-08-20T11:00:00Z"
}
```

#### Collection Activity

```json
{
  "id": 6,
  "user_id": 2,
  "user_name": "John Doe",
  "user_avatar_url": "https://example.com/avatar.jpg",
  "activity_type": "collection",
  "activity_data": {
    "collection_id": 3,
    "collection_name": "My Favorite Coffee Shops"
  },
  "created_at": "2025-08-20T11:15:00Z"
}
```

### Activity Feed Features

#### 1. **Social Timeline**

- Real-time updates from followed users
- Chronological ordering (newest first)
- Rich activity data with context

#### 2. **Privacy Controls**

- Only shows activities from users you follow
- Respects check-in visibility settings
- User-specific activity access control

#### 3. **Advanced Filtering**

- Filter by activity types
- Filter by specific users
- Time-based filtering (since/until)
- Pagination support

#### 4. **Activity Types**

- **Check-ins**: New place check-ins
- **Likes**: Reactions to check-ins
- **Comments**: Comments on check-ins
- **Follows**: New follow relationships
- **Reviews**: Place reviews
- **Collections**: Check-in collections

#### 5. **Performance Optimized**

- Efficient database queries
- Indexed activity types and timestamps
- Pagination for large datasets
- Lazy loading of user information

### Integration with Other Features

#### Automatic Activity Creation

Activities are automatically created when users:

- Create check-ins
- Like check-ins
- Comment on check-ins
- Follow other users
- Post reviews
- Create collections

#### WebSocket Integration

Activity feed can be enhanced with real-time updates via WebSocket notifications.

#### Privacy Enforcement

- Activities respect check-in visibility settings
- Users can only see activities from users they follow
- Personal activities are private by default

### Activity Feed Response Format

```json
{
  "items": [
    {
      "id": 1,
      "user_id": 2,
      "user_name": "John Doe",
      "user_avatar_url": "https://example.com/avatar.jpg",
      "activity_type": "checkin",
      "activity_data": {
        "checkin_id": 42,
        "place_name": "Coffee Shop",
        "note": "Great coffee here!"
      },
      "created_at": "2025-08-20T10:30:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### Activity Feed Use Cases

#### 1. **Social Discovery**

- Discover new places through friends' check-ins
- See what places your network is visiting
- Find trending locations in your area

#### 2. **Engagement**

- React to friends' activities
- Comment on interesting check-ins
- Follow users with similar interests

#### 3. **Content Discovery**

- Browse friends' reviews and recommendations
- Explore collections created by followed users
- Find new places to visit

#### 4. **Social Connection**

- Stay updated on friends' activities
- Engage with shared experiences
- Build community around places

### Activity Feed Best Practices

#### 1. **Performance**

- Use pagination for large feeds
- Implement caching for frequently accessed data
- Optimize database queries with proper indexing

#### 2. **Privacy**

- Respect user privacy settings
- Only show appropriate activities
- Allow users to control their activity visibility

#### 3. **User Experience**

- Provide clear activity descriptions
- Include relevant context and metadata
- Support filtering and search

#### 4. **Content Quality**

- Ensure activity data is accurate
- Provide meaningful activity descriptions
- Include relevant place and user information

## WebSocket Real-time Features

The Circles app provides comprehensive real-time features via WebSocket connections for instant messaging, notifications, and live updates.

### WebSocket Endpoints

#### DM Thread WebSocket

**Connect:** `ws://localhost:8000/ws/dms/{thread_id}?token={jwt_token}`

Real-time messaging for direct message threads with the following features:

- **Authentication**: JWT token required in query parameter
- **Authorization**: Only thread participants can connect
- **Message Types**: Text messages, typing indicators, read receipts, reactions
- **Presence**: Online/offline status updates
- **Auto-reconnection**: Built-in reconnection with exponential backoff

#### User Notifications WebSocket

**Connect:** `ws://localhost:8000/ws/user/{user_id}?token={jwt_token}`

User-wide notifications and updates:

- **Global Notifications**: Follow requests, system messages, activity updates
- **Real-time Updates**: Instant notification delivery
- **Multi-device Support**: Multiple connections per user

### WebSocket Message Types

#### Client to Server Messages

```javascript
// Send a message
{
  "type": "message",
  "text": "Hello, world!"
}

// Send typing indicator
{
  "type": "typing",
  "typing": true
}

// Mark messages as read
{
  "type": "mark_read"
}

// Send message reaction
{
  "type": "reaction",
  "message_id": 123,
  "reaction": "❤️"
}

// Keep connection alive
{
  "type": "ping"
}
```

#### Server to Client Messages

```javascript
// Connection established
{
  "type": "connection_established",
  "thread_id": 456,
  "user_id": 123,
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Thread information
{
  "type": "thread_info",
  "participants": [
    {
      "id": 123,
      "name": "John Doe",
      "avatar_url": "https://example.com/avatar.jpg"
    }
  ],
  "other_user_online": true,
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// New message
{
  "type": "message",
  "message": {
    "id": 789,
    "thread_id": 456,
    "sender_id": 123,
    "text": "Hello, world!",
    "created_at": "2025-08-20T11:44:58.094385Z",
    "sender_info": {
      "id": 123,
      "name": "John Doe",
      "avatar_url": "https://example.com/avatar.jpg"
    }
  },
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Typing indicator
{
  "type": "typing",
  "user_id": 123,
  "typing": true,
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Presence update
{
  "type": "presence",
  "user_id": 123,
  "online": true,
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Read receipt
{
  "type": "read_receipt",
  "user_id": 123,
  "last_read_at": "2025-08-20T11:44:58.094385Z",
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Message reaction
{
  "type": "reaction",
  "message_id": 789,
  "user_id": 123,
  "reaction": "❤️",
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Notification
{
  "type": "notification",
  "notification_type": "new_follower",
  "data": {
    "follower": {
      "id": 456,
      "name": "Jane Smith"
    },
    "message": "Jane Smith started following you"
  },
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Error message
{
  "type": "error",
  "detail": "Empty message",
  "timestamp": "2025-08-20T11:44:58.094385Z"
}

// Pong response
{
  "type": "pong",
  "timestamp": "2025-08-20T11:44:58.094385Z"
}
```

### Real-time Features

#### 1. **Instant Messaging**

- Real-time message delivery
- Message echo to sender
- Message persistence in database
- Support for text messages

#### 2. **Typing Indicators**

- Real-time typing status
- 5-second timeout for typing indicators
- Visual feedback for users

#### 3. **Presence System**

- Online/offline status
- Last seen tracking
- Real-time presence updates
- Multi-device presence support

#### 4. **Read Receipts**

- Message read status
- Last read timestamp
- Real-time read receipt delivery

#### 5. **Message Reactions**

- Heart reactions (❤️)
- Real-time reaction updates
- Reaction persistence

#### 6. **Notifications**

- Follow notifications
- Check-in notifications
- Like notifications
- Comment notifications
- DM request notifications
- System notifications

#### 7. **Connection Management**

- Automatic reconnection
- Exponential backoff
- Connection health monitoring
- Stale connection cleanup
- Ping/pong heartbeat

### WebSocket Client Example

See `docs/websocket_client_example.js` for a complete JavaScript client implementation.

#### Basic Usage:

```javascript
const client = new CirclesWebSocketClient();

// Initialize with token and user ID
client.init("your-jwt-token", 123);

// Connect to a DM thread
client.connectToThread(456);

// Register event handlers
client.on("message", ({ source, data }) => {
  console.log(`New message:`, data.message);
});

client.on("typing", ({ source, data }) => {
  console.log(`User ${data.user_id} is typing`);
});

client.on("presence", ({ source, data }) => {
  console.log(`User ${data.user_id} is ${data.online ? "online" : "offline"}`);
});

// Send a message
client.sendMessage(456, "Hello, world!");

// Send typing indicator
client.sendTyping(456, true);

// Mark as read
client.markAsRead(456);
```

### WebSocket Service Integration

The `WebSocketService` provides methods for sending notifications and updates from the backend:

```python
from app.services.websocket_service import WebSocketService

# Send follow notification
await WebSocketService.send_follow_notification(user_id, follower_data)

# Send check-in notification
await WebSocketService.send_checkin_notification(user_id, checkin_data)

# Send like notification
await WebSocketService.send_like_notification(user_id, like_data)

# Send system notification
await WebSocketService.send_system_notification(user_id, "Welcome!", "Welcome to Circles!")

# Check if user is online
is_online = WebSocketService.is_user_online(user_id)
```

### Connection Security

- **Authentication**: JWT token required for all connections
- **Authorization**: Users can only connect to their own threads
- **Rate Limiting**: Built-in protection against spam
- **Input Validation**: All messages validated before processing
- **Error Handling**: Graceful error handling and recovery

### Performance Features

- **Connection Pooling**: Efficient connection management
- **Background Cleanup**: Automatic stale connection removal
- **Memory Management**: Proper cleanup of disconnected users
- **Scalability**: Designed for horizontal scaling
- **Heartbeat**: Ping/pong to detect connection health

### Browser Support

- Modern browsers with WebSocket support
- Automatic reconnection on connection loss
- Fallback handling for unsupported features
- Progressive enhancement approach

## Development

### Database Migrations

Create a new migration:

```bash
alembic revision --autogenerate -m "Description of changes"
```

Apply migrations:

```bash
uv run alembic upgrade heads
```

### Environment Variables

Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@127.0.0.1:5432/circles

# JWT
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=30

# OTP
OTP_SECRET_KEY=your-secret-key-change-in-production
OTP_EXPIRY_MINUTES=10

# Storage (S3)
STORAGE_BACKEND=s3  # or "local"
S3_BUCKET=your-bucket-name
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_PUBLIC_BASE_URL=https://your-bucket.s3.amazonaws.com
S3_USE_PATH_STYLE=false

# Geo
USE_POSTGIS=true  # Enable PostGIS for geospatial features

# Check-in Proximity Enforcement
CHECKIN_ENFORCE_PROXIMITY=true  # Enable/disable proximity checks
CHECKIN_MAX_DISTANCE_METERS=500  # Maximum distance in meters

# Metrics
METRICS_TOKEN=your-metrics-token  # Protect /metrics endpoint

# App Settings
DEBUG=false
LOG_SAMPLING_RATE=0.1  # Log sampling rate (0.0 to 1.0)
```

### OTP Rate Limiting

`POST /auth/request-otp` is throttled per email+IP:

- Default: 5 requests per minute
- Burst cap: 10 requests across 5 minutes

On limit exceeded, the API returns `429 Too Many Requests` with a descriptive message.

## Project Structure

```
circles/
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration settings
│   ├── database.py        # Database connection and session
│   ├── main.py           # FastAPI application
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py        # Pydantic schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py       # Authentication endpoints
│   │   ├── places.py     # Places, reviews, check-ins, photos
│   │   ├── follow.py     # Follow/Followers
│   │   ├── dms.py        # Direct messages
│   │   ├── collections.py# Check-in collections
│   │   ├── settings.py   # Privacy settings
│   │   ├── users.py      # Profiles, interests, user content
│   │   └── support.py    # Support tickets
│   │   └── health.py     # Health check endpoint
│   └── services/
│       ├── __init__.py
│       ├── otp_service.py # OTP generation and validation
│       ├── jwt_service.py # JWT utilities
│       └── storage.py     # File storage (local/S3)
├── alembic/              # Database migrations
├── tests/               # Test files
├── docker-compose.yml   # PostgreSQL setup
├── pyproject.toml       # Project dependencies
└── README.md
```

## Testing

Run tests:

```bash
uv run pytest
```

## Sample Data

The application includes scripts to populate the database with sample data for testing and development:

### Populate Sample Data

```bash
# Using Docker (recommended)
docker exec circles_app uv run python scripts/populate_sample_data.py

# Using local environment
uv run python scripts/populate_sample_data.py
```

This script creates:

- 20 sample users with various privacy settings
- 8 sample places in New York City
- Follow relationships between users
- Collections with check-ins
- DM threads and messages
- Activities and support tickets
- Comments and likes on check-ins

### Clear Database

To clear all data and start fresh:

```bash
# Using Docker
docker exec circles_app uv run python scripts/clear_database.py

# Using local environment
uv run python scripts/clear_database.py
```

⚠️ **Warning**: This will delete ALL data from the database. Use with caution.

### Sample Data Summary

After running the populate script, you'll have:

- **Users**: 20 sample users with realistic profiles
- **Places**: 8 popular locations in NYC
- **Check-ins**: 5-15 check-ins per user
- **Collections**: 2-4 collections per user
- **DMs**: Threads and messages between users
- **Activities**: Feed entries for social interactions
- **Support Tickets**: Sample support requests

The sample data includes various privacy settings and visibility options to test all application features.

## Notes

- OTP codes are currently returned in the response for development purposes
- In production, implement proper email/SMS delivery for OTP codes
- JWT tokens are issued and required for auth endpoints
- Database tables are created automatically on application startup; DB constraints managed via Alembic
