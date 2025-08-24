# Circles Application - Request Flow Documentation

## Overview

This document describes the complete flow of requests through the Circles application, from client to database and back. Understanding this flow is crucial for debugging, optimization, and system maintenance.

## Table of Contents

1. [General Request Flow](#general-request-flow)
2. [Authentication Flow](#authentication-flow)
3. [Protected Endpoint Flow](#protected-endpoint-flow)
4. [File Upload Flow](#file-upload-flow)
5. [WebSocket Flow](#websocket-flow)
6. [Database Flow](#database-flow)
7. [Error Handling Flow](#error-handling-flow)
8. [Rate Limiting Flow](#rate-limiting-flow)
9. [External API Flow](#external-api-flow)

---

## General Request Flow

```
Client Request
     ↓
[1] FastAPI Application (main.py)
     ↓
[2] Middleware Stack
     ↓
[3] Router Matching
     ↓
[4] Dependency Injection
     ↓
[5] Request Validation (Pydantic)
     ↓
[6] Business Logic (Service Layer)
     ↓
[7] Database Operations
     ↓
[8] Response Serialization
     ↓
[9] Response Middleware
     ↓
Client Response
```

### Detailed Steps:

#### 1. FastAPI Application Entry Point

```python
# app/main.py
app = FastAPI(
    title="Circles API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)
```

#### 2. Middleware Stack (Order Matters)

```python
# Middleware execution order (bottom to top):
app.add_middleware(ErrorHandlingMiddleware)      # Last (handles all errors)
app.add_middleware(LoggingMiddleware)            # Logs requests/responses
app.add_middleware(CORSMiddleware)               # CORS handling
```

#### 3. Router Matching

```python
# app/main.py - Router registration
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(onboarding_router, prefix="/onboarding", tags=["Onboarding"])
app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(places_router, prefix="/places", tags=["Places"])
app.include_router(dms_router, prefix="/dms", tags=["Direct Messages"])
app.include_router(follow_router, prefix="/follow", tags=["Following"])
app.include_router(collections_router, prefix="/collections", tags=["Collections"])
app.include_router(activity_router, prefix="/activity", tags=["Activity"])
app.include_router(settings_router, prefix="/settings", tags=["Settings"])
app.include_router(support_router, prefix="/support", tags=["Support"])
app.include_router(health_router, prefix="/health", tags=["Health"])
```

---

## Authentication Flow

### Email OTP Authentication Flow

```
Client: POST /auth/request-otp
     ↓
[1] Request Validation (EmailRequest)
     ↓
[2] Rate Limiting Check
     ↓
[3] OTP Generation (OTPService)
     ↓
[4] Email Sending (EmailService)
     ↓
[5] Database Storage (OTPCode)
     ↓
Response: {"message": "OTP sent"}

Client: POST /auth/verify-otp
     ↓
[1] Request Validation (OTPVerificationRequest)
     ↓
[2] Rate Limiting Check
     ↓
[3] OTP Verification (OTPService.verify_otp)
     ↓
[4] User Creation/Retrieval
     ↓
[5] JWT Token Generation
     ↓
Response: {"access_token": "jwt", "token_type": "bearer"}
```

### Phone OTP Authentication Flow

```
Client: POST /onboarding/request-phone-otp
     ↓
[1] Request Validation (PhoneOTPRequest)
     ↓
[2] Rate Limiting Check
     ↓
[3] Phone Number Validation
     ↓
[4] Existing OTP Invalidation
     ↓
[5] New OTP Generation
     ↓
[6] Database Storage
     ↓
Response: {"message": "OTP sent to phone"}

Client: POST /onboarding/verify-phone-otp
     ↓
[1] Request Validation (PhoneOTPVerificationRequest)
     ↓
[2] Rate Limiting Check (Brute Force Protection)
     ↓
[3] OTP Verification
     ↓
[4] User Creation/Update
     ↓
Response: {"message": "Phone verified"}
```

---

## Protected Endpoint Flow

### Standard Protected Endpoint

```
Client: GET /users/me (with Authorization header)
     ↓
[1] JWT Token Extraction
     ↓
[2] Token Validation (JWTService.get_current_user)
     ↓
[3] User Retrieval from Database
     ↓
[4] Permission Check (if applicable)
     ↓
[5] Business Logic Execution
     ↓
[6] Database Query (if needed)
     ↓
[7] Response Serialization
     ↓
Response: User profile data
```

### Privacy-Protected Endpoint

```
Client: GET /users/{user_id}/checkins
     ↓
[1] JWT Authentication
     ↓
[2] User Retrieval (target user)
     ↓
[3] Privacy Check (can_view_checkin)
     ↓
[4] Visibility Filtering
     ↓
[5] Pagination Application
     ↓
[6] Database Query with Filters
     ↓
[7] Response Serialization
     ↓
Response: Filtered check-ins list
```

---

## File Upload Flow

### Avatar Upload Flow

```
Client: POST /users/me/avatar (multipart/form-data)
     ↓
[1] JWT Authentication
     ↓
[2] File Validation (content-type, size)
     ↓
[3] Image Processing (Pillow validation)
     ↓
[4] Storage Backend Selection (S3 vs Local)
     ↓
[5] File Storage (async operation)
     ↓
[6] Database Update (avatar_url)
     ↓
[7] Response Serialization
     ↓
Response: Updated user profile
```

### Check-in Photo Upload Flow

```
Client: POST /places/check-ins/full (with photos)
     ↓
[1] JWT Authentication
     ↓
[2] Request Validation (CheckInFullRequest)
     ↓
[3] Proximity Check (500m radius)
     ↓
[4] Rate Limiting Check (5-minute cooldown)
     ↓
[5] Check-in Creation
     ↓
[6] Photo Processing (streaming upload)
     ↓
[7] Storage Operations (async)
     ↓
[8] Database Updates
     ↓
[9] Activity Creation
     ↓
Response: Created check-in with photo URLs
```

---

## WebSocket Flow

### WebSocket Connection Flow

```
Client: WebSocket /ws/dms/{thread_id}
     ↓
[1] Query Parameter Validation (token)
     ↓
[2] JWT Token Verification
     ↓
[3] Thread Access Validation
     ↓
[4] Connection Manager Registration
     ↓
[5] Existing Connection Cleanup
     ↓
[6] WebSocket Acceptance
     ↓
[7] Presence Broadcast
     ↓
Connection Established
```

### Real-time Message Flow

```
Client: WebSocket Message
     ↓
[1] Message Validation (JSON schema)
     ↓
[2] Message Type Routing
     ↓
[3] Business Logic Execution
     ↓
[4] Database Operations
     ↓
[5] Concurrent Broadcast (asyncio.gather)
     ↓
[6] Timeout Protection (5s)
     ↓
[7] Error Handling
     ↓
Response: Broadcast to all participants
```

---

## Database Flow

### Read Operation Flow

```
Service Layer Request
     ↓
[1] Database Session Creation (AsyncSession)
     ↓
[2] SQLAlchemy Query Construction
     ↓
[3] Query Execution (await db.execute())
     ↓
[4] Result Processing (scalars().all())
     ↓
[5] Session Cleanup
     ↓
[6] Data Serialization
     ↓
Response Data
```

### Write Operation Flow

```
Service Layer Request
     ↓
[1] Database Session Creation
     ↓
[2] Model Instance Creation/Update
     ↓
[3] Session Add/Update
     ↓
[4] Transaction Commit (await db.commit())
     ↓
[5] Model Refresh (await db.refresh())
     ↓
[6] Session Cleanup
     ↓
[7] Response Serialization
     ↓
Response Data
```

### Complex Query Flow (with Joins)

```
Service Layer Request
     ↓
[1] Database Session Creation
     ↓
[2] Complex Query Construction
     ↓
[3] Join Operations
     ↓
[4] Filter Application
     ↓
[5] Pagination
     ↓
[6] Query Execution
     ↓
[7] Result Processing
     ↓
[8] Session Cleanup
     ↓
Response Data
```

---

## Error Handling Flow

### Standard Error Flow

```
Exception Occurs
     ↓
[1] Exception Capture (try/catch)
     ↓
[2] Error Logging (logger.error)
     ↓
[3] Error Classification
     ↓
[4] HTTP Status Code Assignment
     ↓
[5] Error Response Creation
     ↓
[6] Error Middleware Processing
     ↓
[7] Response Serialization
     ↓
Client Error Response
```

### Validation Error Flow

```
Invalid Request Data
     ↓
[1] Pydantic Validation Error
     ↓
[2] FastAPI Validation Handler
     ↓
[3] Error Response Creation
     ↓
[4] Error Middleware Processing
     ↓
[5] Response Serialization
     ↓
Client Validation Error Response
```

---

## Rate Limiting Flow

### OTP Rate Limiting

```
Client Request
     ↓
[1] Rate Limiting Check
     ↓
[2] In-Memory Counter Update
     ↓
[3] Time Window Validation
     ↓
[4] Limit Enforcement
     ↓
[5] Request Processing (if allowed)
     ↓
[6] Rate Limit Response (if exceeded)
     ↓
Response
```

### Check-in Rate Limiting

```
Client Request
     ↓
[1] User Rate Limit Check
     ↓
[2] Database Query (last check-in time)
     ↓
[3] Time Difference Calculation
     ↓
[4] Cooldown Enforcement (5 minutes)
     ↓
[5] Request Processing (if allowed)
     ↓
[6] Rate Limit Response (if exceeded)
     ↓
Response
```

---

## External API Flow

### Foursquare API Integration

```
Service Request
     ↓
[1] API Key Validation
     ↓
[2] Request Preparation
     ↓
[3] HTTP Client Creation (httpx.AsyncClient)
     ↓
[4] Request Execution (with timeout)
     ↓
[5] Response Validation
     ↓
[6] Error Handling
     ↓
[7] Data Processing
     ↓
[8] Database Storage
     ↓
Response Data
```

### OpenStreetMap API Integration

```
Service Request
     ↓
[1] Request Preparation
     ↓
[2.1] Overpass API Query Construction
     ↓
[2.2] Nominatim API Query Construction
     ↓
[3] HTTP Client Creation
     ↓
[4] Request Execution (with retry logic)
     ↓
[5] Response Validation
     ↓
[6] Error Handling
     ↓
[7] Data Processing
     ↓
[8] Database Storage
     ↓
Response Data
```

---

## Request Flow Examples

### Example 1: User Check-in Flow

```
1. Client: POST /places/check-ins/full
   - Headers: Authorization: Bearer <jwt>
   - Body: Multipart form with location, photos

2. FastAPI Router: places_router
   - Endpoint: create_check_in_full
   - Dependencies: get_current_user, get_db

3. Authentication: JWTService.get_current_user
   - Token extraction and validation
   - User retrieval from database

4. Request Validation: CheckInFullRequest
   - Pydantic model validation
   - File validation

5. Business Logic: Check-in creation
   - Proximity validation (500m)
   - Rate limiting check
   - Photo processing (streaming)

6. Database Operations:
   - Check-in record creation
   - Photo URL storage
   - Activity record creation

7. Response: CheckInResponse
   - Serialized check-in data
   - Photo URLs
   - Success message
```

### Example 2: Real-time DM Flow

```
1. Client: WebSocket /ws/dms/{thread_id}?token=<jwt>

2. WebSocket Connection:
   - Token validation
   - Thread access verification
   - Connection manager registration

3. Client: Send message
   - JSON payload with message content

4. Message Processing:
   - Message validation
   - Database storage
   - Participant retrieval

5. Broadcast:
   - Concurrent message delivery
   - Timeout protection
   - Error handling

6. Response: Broadcast to all participants
   - Message data
   - Timestamp
   - Sender information
```

---

## Performance Considerations

### Database Optimization

- **Connection Pooling**: AsyncSession with connection pool
- **Query Optimization**: Proper indexing, selectinload for relationships
- **Transaction Management**: Proper commit/rollback handling

### Memory Management

- **Streaming Uploads**: 64KB chunks for file uploads
- **Async Operations**: Non-blocking I/O operations
- **Connection Cleanup**: Proper session and connection cleanup

### Caching Strategy

- **Rate Limiting**: In-memory counters with TTL
- **User Sessions**: JWT tokens with expiration
- **External API**: TTL-based caching for place data

---

## Security Considerations

### Authentication Flow

- **JWT Validation**: Token signature and expiration verification
- **Rate Limiting**: Per-endpoint and per-user rate limits
- **Input Validation**: Pydantic models for all inputs

### Privacy Flow

- **Visibility Checks**: Privacy-based data filtering
- **Permission Validation**: User permission enforcement
- **Data Sanitization**: Sensitive data protection

### File Upload Security

- **Content Validation**: File type and size validation
- **Image Processing**: Pillow-based image validation
- **Storage Security**: Secure file storage with access controls

---

## Monitoring and Logging

### Request Logging

```python
# LoggingMiddleware logs:
- Request method and path
- Request duration
- Response status code
- User ID (if authenticated)
- Request size
- Response size
```

### Error Logging

```python
# ErrorHandlingMiddleware logs:
- Exception details
- Stack trace
- Request context
- User information
- Error classification
```

### Performance Metrics

```python
# Metrics collection:
- Request duration
- Database query time
- External API response time
- Memory usage
- Error rates
```

---

## Troubleshooting Guide

### Common Issues and Flow Debugging

#### 1. Authentication Failures

```
Check Flow:
1. JWT token extraction
2. Token signature validation
3. Token expiration check
4. User database lookup
5. User status validation
```

#### 2. Database Connection Issues

```
Check Flow:
1. Connection pool status
2. Database availability
3. Query execution
4. Transaction handling
5. Session cleanup
```

#### 3. File Upload Issues

```
Check Flow:
1. File validation
2. Storage backend selection
3. File processing
4. Storage operation
5. Database update
```

#### 4. WebSocket Connection Issues

```
Check Flow:
1. Token validation
2. Thread access verification
3. Connection manager registration
4. WebSocket acceptance
5. Message processing
```

---

This documentation provides a comprehensive understanding of how requests flow through the Circles application, enabling effective debugging, optimization, and system maintenance.
