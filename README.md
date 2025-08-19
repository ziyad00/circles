# Circles - OTP Auth + Places/Check-Ins API

A FastAPI application with OTP (One-Time Password) authentication and core Places/Check-Ins features, backed by PostgreSQL.

## Features

- OTP-based authentication (email)
- JWT issuance and authenticated endpoints
- Core Places: create, search (filters), trending
- Check-Ins with 24h visibility window and basic rate-limiting
- Saved places lists
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

3. **Start PostgreSQL database**

   ```bash
   docker-compose up -d postgres
   ```

4. **Run database migrations**

   ```bash
   alembic upgrade head
   ```

5. **Start the application**
   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

The API will be available at `http://localhost:8000`

## API Endpoints

### Authentication

- `POST /auth/request-otp` - Request an OTP code
- `POST /auth/verify-otp` - Verify OTP code and authenticate

### Health Check

- `GET /health` - Health check endpoint

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

#### Get Place

GET `/places/{id}`

```bash
curl http://localhost:8000/places/1
```

#### Search Places (paginated)

GET `/places/search?query=&city=&neighborhood=&category=&rating_min=&limit=20&offset=0`

```bash
curl 'http://localhost:8000/places/search?city=San%20Francisco&limit=10&offset=0'
```

Returns `{ items, total, limit, offset }` with `items` as `PlaceResponse[]`.

#### Trending Places (paginated)

GET `/places/trending?city=&category=&hours=24&limit=10&offset=0`

```bash
curl 'http://localhost:8000/places/trending?city=San%20Francisco&hours=24&limit=10'
```

Returns `{ items, total, limit, offset }` ranked by recent check-ins.

#### Check-In (auth)

POST `/places/check-ins`

```bash
curl -X POST http://localhost:8000/places/check-ins \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"place_id":1, "note":"Latte time", "visibility":"public"}'
```

Rate limiting: prevents repeat check-ins to the same place by same user within 5 minutes (429).

#### Who's Here (last 24h)

GET `/places/{id}/whos-here`

```bash
curl http://localhost:8000/places/1/whos-here
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

## Development

### Database Migrations

Create a new migration:

```bash
alembic revision --autogenerate -m "Description of changes"
```

Apply migrations:

```bash
alembic upgrade head
```

### Environment Variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost/circles
# OTP is generated internally for development; set a proper secret in prod
OTP_SECRET_KEY=your-secret-key-change-in-production
OTP_EXPIRY_MINUTES=10
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=30
```

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
│   │   └── health.py     # Health check endpoint
│   └── services/
│       ├── __init__.py
│       └── otp_service.py # OTP generation and validation
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

## Notes

- OTP codes are currently returned in the response for development purposes
- In production, implement proper email/SMS delivery for OTP codes
- JWT tokens are prepared for future implementation
- Database tables are created automatically on application startup
