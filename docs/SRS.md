## Circles Backend — Software Requirements Specification (SRS)

### 1. Overview

Circles is a social location backend built on FastAPI and PostgreSQL/PostGIS. Users authenticate with phone numbers, check in to places, follow others, exchange direct messages, and discover trending places. The system supports both internal activity-based trending and Foursquare-based discovery via a configurable override/fallback.

### 2. Goals

- Provide secure, phone-only authentication and onboarding
- Support place discovery (search, suggestions, trending) and activity (check-ins, reviews, photos)
- Enable social graph (follow/followers), DMs (REST + WebSockets), and ephemeral place chat (check-in–gated)
- Operate reliably in AWS (ECS Fargate, RDS Postgres, ALB), with infrastructure defined in Terraform
- Expose clear, consistent REST APIs with OpenAPI/Swagger docs

### 4. User Roles & Personas

- End User: uses mobile/web client to onboard, check in, discover places, follow, and message
- Admin (future): operational tasks (out of scope for current APIs)

### 5. System Context

- API: FastAPI (async), Pydantic v2 schemas, SQLAlchemy async ORM
- Data: PostgreSQL (RDS) with optional PostGIS features
- Infra: AWS ECS Fargate, ALB, VPC (public/private subnets), Secrets Manager, CloudWatch Logs, S3 for media
- External: Foursquare Places API (optional, for trending override/fallback/enrichment), OSM Overpass (seed)

### 6. Functional Requirements

#### 6.1 Authentication & Onboarding

- Phone-only OTP flow:
  - POST /onboarding/request-otp: request SMS OTP (debug returns code when APP_DEBUG=true)
  - POST /onboarding/verify-otp: verify OTP; returns JWT access token
- Username validation and onboarding setup (names, interests optional)
- GET /auth/me: returns current user profile (id, phone, username, follower/following counts)

Constraints:

- OTP expiry: configurable (APP_OTP_EXPIRY_MINUTES)
- Rate limiting for OTP: configurable (APP_OTP_RATE_LIMIT_ENABLED and limits)

#### 6.2 Users & Profiles

- Search users (filters: q, has_avatar, interests)
- Update profile name/bio; upload avatar
- Get public user profile: `/users/{user_id}` includes username and follower/following counts
- List user check-ins with visibility enforcement: `/users/{user_id}/check-ins`
- List user media (review/check-in photos), visibility-aware

#### 6.3 Follow System

- Follow/unfollow users
- List followers/following
- Responses include username, bio, avatar_url; follow endpoints return { followed: boolean }

#### 6.4 Places & Discovery

- Search places, filter options, quick search, enrich by external data
- Trending:
  - Internal trending (activity-based) with optional city filter
  - Foursquare override (APP_FSQ_TRENDING_OVERRIDE=true) or fallback (APP_FSQ_TRENDING_ENABLED=true)
  - City-based FSQ trending: `/places/trending?city=...` or global variant
  - Internal trending parameters: time_window (1h/6h/24h/7d/30d), pagination; optional proximity re-rank

Activity Signals for internal trending:

- Check-ins (3 pts), Reviews (2 pts), Photos (1 pt), Unique users (2 pts)

#### 6.5 Check-ins & Media

- Create check-in (requires latitude/longitude and proximity to place unless disabled)
- Visibility: public, friends (followers), private
- Rate limit: 5-minute cooldown on same place per user
- Retrieve check-in detail/stats, like/unlike, comments list/add
- Media: upload check-in/review photos (caps by APP\_\*\_MAX_MB)

Proximity Enforcement:

- Configurable radius (APP_CHECKIN_MAX_DISTANCE_METERS, default 500; currently 1000 in AWS)
- Toggle via APP_CHECKIN_ENFORCE_PROXIMITY

#### 6.6 Direct Messages (DMs)

- REST for inbox, requests, messages; presence, typing, read states
- WebSockets:
  - `/ws/dms/{thread_id}` for thread-level real-time messaging
  - `/ws/user/{user_id}` for user-wide events
  - Auth: token in query param `?token=`

#### 6.7 Place Chat (Ephemeral)

- WebSocket: `/ws/places/{place_id}/chat`
- Access control: must have a check-in within a configurable window (APP_PLACE_CHAT_WINDOW_HOURS, default 12)
- Live-only; no persistence of message history

### 7. Data Model (High Level)

- User(id, phone, username, is_verified, name, bio, avatar_url, dm_privacy, created_at, ...)
- Place(id, name, address, city, neighborhood, latitude, longitude, categories, rating, external_id, data_source, ...)
- CheckIn(id, user_id, place_id, note, visibility, created_at, expires_at, photo_url)
- Photo(id, user_id, place_id, review_id?, url, caption, created_at)
- Review(id, user_id, place_id, rating, text, created_at)
- Follow(id, follower_id, followee_id, created_at)
- DMThread, DMMessage, DMParticipantState (presence, mute, block, typing)

Notes:

- Categories sourced from OSM or FSQ; FSQ takes precedence when enriched/overridden
- City backfill and enrichment processes exist to improve completeness

### 8. Non-Functional Requirements

- Performance: p95 API latency under typical load (<300ms for common read endpoints)
- Availability: target 99.9% for API under normal operations
- Scalability: ECS desired_count and task definition updatable via Terraform
- Security: JWT-based auth; all secrets in AWS Secrets Manager
- Observability: CloudWatch Logs for app; health endpoint for ALB

### 9. Configuration (Environment Variables)

Prefix: `APP_`

- Core: DEBUG, DATABASE_URL, CORS_ALLOWED_ORIGINS
- Auth/OTP: OTP_SECRET_KEY, OTP_EXPIRY_MINUTES, OTP_RATE_LIMIT_ENABLED, OTP_REQUESTS_PER_MINUTE, OTP_REQUESTS_BURST
- JWT: JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_MINUTES
- Storage: STORAGE_BACKEND, S3_BUCKET, S3_REGION, S3_PUBLIC_BASE_URL, S3_USE_PATH_STYLE
- Geo/Check-ins: USE_POSTGIS, CHECKIN_ENFORCE_PROXIMITY, CHECKIN_MAX_DISTANCE_METERS
- DMs: DM_REQUESTS_PER_MIN, DM_MESSAGES_PER_MIN, WS_SEND_TIMEOUT_SECONDS
- External Suggestions/Overpass: EXTERNAL_SUGGESTIONS_RADIUS_M, OVERPASS_ENDPOINTS, OVERPASS_TIMEOUT_SECONDS
- Enrichment: ENRICH_TTL_HOT_DAYS, ENRICH_TTL_COLD_DAYS, ENRICH_MAX_DISTANCE_M, ENRICH_MIN_NAME_SIM
- Foursquare: FOURSQUARE_API_KEY, FSQ_TRENDING_ENABLED, FSQ_TRENDING_OVERRIDE, FSQ_TRENDING_RADIUS_M
- Auto-seed: AUTOSEED_ENABLED, AUTOSEED_MIN_OSM_COUNT
- Upload Limits: AVATAR_MAX_MB, PHOTO_MAX_MB
- Place Chat: PLACE_CHAT_WINDOW_HOURS
- Logging/metrics: LOG_SAMPLE_RATE, METRICS_TOKEN

### 10. External Integrations

- Foursquare: v3 Places Search for trending approximation and enrichment
  - When override is ON, trending uses FSQ only (city or lat/lng)
  - When override is OFF, internal trending uses FSQ only as fallback
- OSM Overpass: used for seeding places by bounding box

### 11. Error Handling & Responses

- Consistent JSON errors with `detail`
- 400 for invalid params (e.g., missing lat/lng when required)
- 401 for auth errors; 403 for visibility violations
- 429 for OTP or action rate limiting

### 12. Rate Limiting

- OTP endpoints controlled via settings with burst/token bucket configuration
- DM message/request per-minute caps enforced by settings

### 13. Security

- JWTs stored client-side and passed via Authorization header
- Secrets in AWS Secrets Manager, not committed to code
- CORS configured for allowed origins
- No email PII; phone numbers unique identifiers

### 14. Deployment Architecture (AWS)

- ECS Fargate service behind ALB in private subnets, public ALB
- RDS PostgreSQL (with PostGIS enabled when configured)
- S3 for media storage in production
- Terraform manages VPC, subnets, security groups, ECS/ECR, RDS, ALB, IAM

### 15. Operational Tasks

- Build & push container (amd64) to ECR
- Update ECS service/task definition via Terraform or CLI
- Seed data via one-off ECS tasks (populate_sample_data, OSM seed, backfills)
- Rotate secrets in Secrets Manager

### 16. Assumptions & Constraints

- Clients pass accurate lat/lng for check-ins; proximity enforced when enabled
- FSQ data requires a valid API key; otherwise FSQ paths return empty
- Place chat is ephemeral; no history endpoint by design

### 17. Acceptance Criteria

- Phone onboarding and JWT issuance works end-to-end
- `/auth/me` returns id, phone, username, followers_count, following_count
- Following/unfollowing returns `{ followed: boolean }`; lists include profile fields
- `/users/{id}/check-ins` respects visibility and returns user’s check-ins
- Trending endpoints operate per configuration:
  - Internal trending returns items when activity exists; respects city filter
  - FSQ override returns FSQ-based items for city or lat/lng
- DM REST/WebSocket flows function for accepted threads; user-wide WS updates arrive
- Place chat WS accepts only recently checked-in users and broadcasts live messages

### 18. Future Work

- Admin tooling and moderation
- Persistent place chat history (if business direction changes)
- Advanced personalization for trending and search
- Webhook or event-stream integrations

### Appendix A — Detailed Requirement Descriptions

#### Functional Requirements (FR)

- FR-001: Phone OTP Request

  - Description: The system shall allow a user to request an OTP via phone number at `POST /onboarding/request-otp`.
  - Constraints: Rate-limited by `APP_OTP_RATE_LIMIT_ENABLED`, `APP_OTP_REQUESTS_PER_MINUTE`, and `APP_OTP_REQUESTS_BURST`.
  - Acceptance Criteria:
    - Returns 200 with `{"status":"sent"}` (and `otp` only when `APP_DEBUG=true`).
    - Returns 429 when rate limit exceeded with specific error message.

- FR-002: Phone OTP Verify & JWT Issuance

  - Description: The system shall verify a submitted OTP at `POST /onboarding/verify-otp` and issue a JWT.
  - Constraints: OTP validity window controlled by `APP_OTP_EXPIRY_MINUTES`.
  - Acceptance Criteria:
    - Valid OTP returns 200 with `access_token` and `token_type`.
    - Invalid/expired OTP returns 400 with `detail` describing the issue.

- FR-003: Get Current User Profile

  - Description: The system shall return the authenticated user’s profile at `GET /auth/me` including `id, phone, username, followers_count, following_count`.
  - Acceptance Criteria:
    - Returns 200 with all listed fields.
    - Requires valid JWT; otherwise returns 401.

- FR-004: Update Profile

  - Description: The system shall allow updating profile fields (e.g., `name`, `bio`, `avatar_url`).
  - Acceptance Criteria:
    - Authenticated request updates fields and returns updated profile.

- FR-005: Search Users

  - Description: The system shall support searching users via `POST /users/search` with filters and return `PublicUserSearchResponse` including `followed`.
  - Acceptance Criteria:
    - Query returns paginated list with `id, username, avatar_url, followed`.

- FR-006: Follow User

  - Description: The system shall allow following a user via `POST /follow/{user_id}` and respond with `{ "followed": true }`.
  - Acceptance Criteria:
    - Following same user twice is idempotent and returns `{ "followed": true }`.

- FR-007: Unfollow User

  - Description: The system shall allow unfollowing a user via `DELETE /follow/{user_id}` and respond with `{ "followed": false }`.
  - Acceptance Criteria:
    - Unfollowing a non-followed user is idempotent and returns `{ "followed": false }`.

- FR-008: List Followers & Following

  - Description: The system shall provide `GET /follow/followers` and `GET /follow/following` including `username, bio, avatar_url` and boolean `followed`.
  - Acceptance Criteria:
    - Responses are paginated and include `followed` status per item.

- FR-009: Create Check-in

  - Description: The system shall allow creating a check-in bound to a place with proximity enforcement based on `APP_CHECKIN_ENFORCE_PROXIMITY` and `APP_CHECKIN_MAX_DISTANCE_METERS`.
  - Acceptance Criteria:
    - Within radius: returns 201 with check-in id.
    - Outside radius (when enforced): returns 400/403 with `detail`.

- FR-010: List User Check-ins

  - Description: The system shall list a user’s check-ins via `GET /users/{user_id}/check-ins` respecting visibility rules.
  - Acceptance Criteria:
    - Returns items, total, limit, offset; excludes private items from non-owners.

- FR-011: Place Search

  - Description: The system shall search places using internal DB with optional external enrichment.
  - Acceptance Criteria:
    - Returns paginated places with ids, names, coordinates, and optional `city`.

- FR-012: Trending (Internal)

  - Description: The system shall compute trending places using recent activity and support `time_window`, `city`, `limit`, and `offset`.
  - Acceptance Criteria:
    - Returns ordered list of places consistent with scoring rules and applied city filter when provided.

- FR-013: Trending (Foursquare Override/Fallback)

  - Description: When `APP_FSQ_TRENDING_OVERRIDE=true`, the system shall return FSQ-based trending; when `APP_FSQ_TRENDING_ENABLED=true` (override=false) and internal results are insufficient, the system shall append/fallback to FSQ.
  - Acceptance Criteria:
    - City param triggers FSQ query by `query=city`; lat/lng uses `ll` and `radius`.

- FR-014: DM Real-time Messaging (WebSocket)

  - Description: The system shall support WS messaging on `/ws/dms/{thread_id}` with token auth and basic events (message, typing, presence).
  - Acceptance Criteria:
    - Authenticated clients can send/receive messages in real time within a thread.

- FR-015: Place Chat (Ephemeral)

  - Description: The system shall provide `/ws/places/{place_id}/chat` for live chat accessible only to users with a recent check-in within `APP_PLACE_CHAT_WINDOW_HOURS`.
  - Acceptance Criteria:
    - No recent check-in → WS closed with code 4403; eligible users can exchange messages broadcast to active participants.

- FR-016: Media Upload

  - Description: The system shall allow upload of check-in/review photos subject to max size settings (`APP_PHOTO_MAX_MB`, etc.).
  - Acceptance Criteria:
    - Oversized media rejected with clear error; accepted media accessible via returned URL.

- FR-017: OpenAPI/Swagger Accuracy
  - Description: The system shall keep Swagger reflecting active endpoints and hide legacy ones.
  - Acceptance Criteria:
    - Email OTP routes not present; hidden endpoints marked `include_in_schema=false`.

#### Non-Functional Requirements (NFR)

- NFR-001: Performance

  - Description: Typical read endpoints shall respond with p95 < 300 ms under normal load.
  - Acceptance Criteria: Load test report demonstrates compliance.

- NFR-002: Availability

  - Description: API shall target 99.9% availability backed by ECS/ALB health checks.
  - Acceptance Criteria: Health checks green; rolling deployments do not drop availability below target.

- NFR-003: Security & Secrets

  - Description: All sensitive config shall be provided via environment variables and AWS Secrets Manager; JWT used for auth.
  - Acceptance Criteria: No secrets in repo; task definition references Secrets Manager for confidential values.

- NFR-004: Observability

  - Description: Application logs shall be shipped to CloudWatch; key actions logged with structured fields.
  - Acceptance Criteria: Logs visible in CloudWatch with request correlation ids where applicable.

- NFR-005: Scalability

  - Description: Service shall scale by adjusting ECS `desired_count` and CPU/memory as needed without code changes.
  - Acceptance Criteria: Increasing desired_count results in multiple healthy tasks behind ALB.

- NFR-006: Portability/Compatibility

  - Description: Containers shall run on `linux/amd64` to be compatible with ECS Fargate.
  - Acceptance Criteria: Images built with `--platform linux/amd64` start successfully in ECS.

- NFR-007: Configurability
  - Description: Behavior shall be controlled via documented `APP_` variables (`.env.example` parity) and remain overrideable by Terraform.
  - Acceptance Criteria: Changing env values updates runtime behavior without code modifications.
