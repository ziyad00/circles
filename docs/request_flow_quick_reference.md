# Request Flow Quick Reference Guide

## 🚀 Quick Start

This guide provides a quick reference for understanding how requests flow through the Circles application.

## 📋 Request Flow Overview

### 1. **General Flow**

```
Client → FastAPI → Middleware → Router → Dependencies → Validation → Business Logic → Database → Response
```

### 2. **Authentication Flow**

```
Request OTP → Rate Limit → Generate OTP → Send Email → Store in DB → Response
Verify OTP → Rate Limit → Validate OTP → Create/Get User → Generate JWT → Response
```

### 3. **Protected Endpoint Flow**

```
Request + JWT → Extract Token → Validate Token → Get User → Check Permissions → Business Logic → Response
```

## 🔍 Debugging Common Issues

### Authentication Issues

```bash
# Check JWT token
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/users/me

# Check OTP request
curl -X POST http://localhost:8000/auth/request-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

### Database Issues

```python
# Check database connection
from app.database import get_db
async with get_db() as db:
    result = await db.execute("SELECT 1")
    print(result.scalar())
```

### File Upload Issues

```bash
# Test file upload
curl -X POST http://localhost:8000/users/me/avatar \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/image.jpg"
```

## 📊 Request Flow Types

### 1. **REST API Requests**

- **Method**: GET, POST, PUT, DELETE
- **Authentication**: JWT Bearer token
- **Validation**: Pydantic models
- **Response**: JSON

### 2. **WebSocket Requests**

- **Connection**: `/ws/dms/{thread_id}?token=JWT`
- **Authentication**: JWT token in query params
- **Messages**: JSON format
- **Real-time**: Bidirectional communication

### 3. **File Upload Requests**

- **Method**: POST with multipart/form-data
- **Authentication**: JWT Bearer token
- **Validation**: File type, size, content
- **Storage**: S3 or local filesystem

## 🔧 Middleware Stack

### Order of Execution (Bottom to Top)

1. **ErrorHandlingMiddleware** - Catches and formats all errors
2. **LoggingMiddleware** - Logs requests and responses
3. **CORSMiddleware** - Handles CORS headers

### Middleware Functions

```python
# Error Handling
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    # Log error and return formatted response

# Logging
@app.middleware("http")
async def log_requests(request, call_next):
    # Log request details and timing

# CORS
app.add_middleware(CORSMiddleware, allow_origins=["*"])
```

## 🗄️ Database Operations

### Read Operations

```python
# Standard read flow
async def get_user(user_id: int, db: AsyncSession):
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
```

### Write Operations

```python
# Standard write flow
async def create_user(user_data: dict, db: AsyncSession):
    user = User(**user_data)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

## 🔒 Security Flow

### Authentication

1. **JWT Token Extraction** - From Authorization header
2. **Token Validation** - Signature and expiration check
3. **User Lookup** - Database query for user
4. **Permission Check** - Role-based access control

### Rate Limiting

1. **Request Check** - In-memory counter
2. **Time Window** - Sliding window validation
3. **Limit Enforcement** - Block if exceeded
4. **Response** - 429 Too Many Requests

### Privacy Protection

1. **Visibility Check** - User privacy settings
2. **Permission Validation** - Can user access data?
3. **Data Filtering** - Apply privacy filters
4. **Response** - Filtered data only

## 📱 Real-time Flow

### WebSocket Connection

1. **Token Validation** - JWT in query params
2. **Thread Access** - Verify user can access thread
3. **Connection Manager** - Register connection
4. **WebSocket Accept** - Establish connection

### Message Flow

1. **Message Validation** - JSON schema validation
2. **Database Storage** - Store message
3. **Concurrent Broadcast** - Send to all participants
4. **Timeout Protection** - 5-second timeout

## 🚨 Error Handling

### Error Types

- **ValidationError** - Invalid request data (400)
- **AuthenticationError** - Invalid credentials (401)
- **PermissionError** - Insufficient permissions (403)
- **NotFoundError** - Resource not found (404)
- **RateLimitError** - Too many requests (429)
- **InternalError** - Server error (500)

### Error Response Format

```json
{
  "error": "Error type",
  "message": "Human readable message",
  "details": "Additional error details",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## 🔍 Monitoring and Logging

### Request Logging

```python
# Logged information
{
  "method": "GET",
  "path": "/users/me",
  "duration": 0.123,
  "status_code": 200,
  "user_id": 123,
  "request_size": 1024,
  "response_size": 2048
}
```

### Error Logging

```python
# Error information
{
  "error_type": "ValidationError",
  "message": "Invalid email format",
  "stack_trace": "...",
  "request_context": {...},
  "user_id": 123
}
```

## 🎯 Performance Optimization

### Database Optimization

- **Connection Pooling** - Reuse database connections
- **Query Optimization** - Use proper indexes
- **Lazy Loading** - Load relationships on demand
- **Batch Operations** - Group database operations

### Memory Management

- **Streaming Uploads** - Process files in chunks
- **Async Operations** - Non-blocking I/O
- **Connection Cleanup** - Proper resource disposal
- **Garbage Collection** - Automatic memory management

### Caching Strategy

- **Rate Limiting** - In-memory counters with TTL
- **User Sessions** - JWT tokens with expiration
- **External API** - TTL-based caching for place data

## 🛠️ Troubleshooting Checklist

### Authentication Issues

- [ ] JWT token valid and not expired
- [ ] Token in correct format (Bearer <token>)
- [ ] User exists in database
- [ ] User account is active

### Database Issues

- [ ] Database connection available
- [ ] Connection pool not exhausted
- [ ] Query syntax correct
- [ ] Proper transaction handling

### File Upload Issues

- [ ] File type allowed (image/\*)
- [ ] File size within limits (10MB)
- [ ] Storage backend configured
- [ ] File content valid

### WebSocket Issues

- [ ] JWT token valid
- [ ] User has access to thread
- [ ] Connection manager working
- [ ] Message format correct

## 📚 Additional Resources

- **Full Documentation**: `docs/request_flow_documentation.md`
- **API Documentation**: `http://localhost:8000/docs`
- **Flow Diagrams**: `scripts/generate_flow_diagrams.py`
- **Testing**: `tests/` directory
- **Configuration**: `app/config.py`

## 🎉 Quick Commands

### Generate Flow Diagrams

```bash
python3 scripts/generate_flow_diagrams.py
```

### Run Tests

```bash
docker exec circles_app uv run pytest
```

### Check API Health

```bash
curl http://localhost:8000/health
```

### View Logs

```bash
docker logs circles_app
```

---

This quick reference guide provides essential information for understanding and debugging request flows in the Circles application. For detailed information, refer to the full documentation.
