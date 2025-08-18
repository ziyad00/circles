# Circles - OTP Authentication API

A FastAPI application with OTP (One-Time Password) authentication using PostgreSQL database.

## Features

- OTP-based authentication
- PostgreSQL database integration
- User registration and verification
- Random 6-digit OTP generation
- Database migrations with Alembic

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
   uv run python -m app.main
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

### 2. Verify OTP

```bash
curl -X POST "http://localhost:8000/auth/verify-otp" \
     -H "Content-Type: application/json" \
     -d '{"email": "user@example.com", "otp_code": "123456"}'
```

Response:

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
  "access_token": null
}
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
