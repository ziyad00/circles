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
  -d '{"place_id":1, "note":"Latte time"}'
```

Rate limiting: prevents repeat check-ins to the same place by same user within 5 minutes (429).

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
# OTP throttling (per email+IP)
APP_OTP_REQUESTS_PER_MINUTE=5
APP_OTP_REQUESTS_BURST=10
# Storage
STORAGE_BACKEND=local  # or s3
LOCAL_STORAGE_PATH=media
S3_BUCKET=your-bucket
S3_REGION=your-region
S3_ENDPOINT_URL=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_PUBLIC_BASE_URL=
S3_USE_PATH_STYLE=true
# CORS
CORS_ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173"]
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

## Notes

- OTP codes are currently returned in the response for development purposes
- In production, implement proper email/SMS delivery for OTP codes
- JWT tokens are issued and required for auth endpoints
- Database tables are created automatically on application startup; DB constraints managed via Alembic
