## Circles Runtime Architecture and Container Image Architecture

- ALB (HTTP:80) forwards to ECS Fargate tasks in private subnets via a target group on port 8000. Health check path: `/health`.
- ECS Fargate service runs the app task definition (awsvpc), no public IP, egress via NAT.
- RDS PostgreSQL 15 in private subnets; security group allows ingress only from ECS tasks.
- S3 bucket stores media/uploads; app uses `APP_STORAGE_BACKEND=s3` in ECS task env.
- Secrets Manager holds application secrets (JWT, OTP, metrics token, DB URL); ECS task is granted `secretsmanager:GetSecretValue` to inject them.
- ECR hosts the application image; ECS task definition pulls `:latest` by default.
- VPC with public subnets for ALB and private subnets for ECS/RDS; one NAT gateway.

### Image architecture: why linux/amd64

- Symptom in CloudWatch logs: `exec /usr/bin/sh: exec format error`.
- Cause: Image built on Apple Silicon (arm64) but ECS Fargate default platform is x86_64 (linux/amd64). Kernel cannot execute arm64 binaries on x86_64.
- Fix: Build and push an amd64 image using Buildx, then force a new ECS deployment.

Build and push (amd64) to ECR:

```bash
# Login to ECR
AWS_REGION=$(cd infra/terraform && terraform output -raw aws_region)
ECR_URL=$(cd infra/terraform && terraform output -raw ecr_repository_url)
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_URL"

# Important: build for linux/amd64 and push
docker buildx build --platform linux/amd64 -t "$ECR_URL:latest" -f Dockerfile . --push

# Redeploy ECS to pull the new image
aws ecs update-service \
  --cluster circles-cluster \
  --service circles-svc \
  --force-new-deployment \
  --region "$AWS_REGION"
```

Notes:

- A `.dockerignore` file excludes Terraform artifacts and local secrets from the build context.
- Multi-arch alternative: build both amd64 and arm64 via `--platform linux/amd64,linux/arm64` and use a manifest; Fargate will pull amd64. This increases build time/size and is optional.

### Verification against ALB

- Quick health check:

```bash
ALB=$(cd infra/terraform && terraform output -raw alb_dns_name)
curl -i "http://$ALB/health"
```

- Full endpoint smoke using the provided script (temporary BASE override):

```bash
ALB=$(cd infra/terraform && terraform output -raw alb_dns_name)
sed "s|BASE = 'http://localhost:8000'|BASE = 'http://$ALB'|" scripts/verify_features.py > /tmp/verify_alb.py
uv run python /tmp/verify_alb.py || python3 /tmp/verify_alb.py
```

Expected in production-like runs:

- Auth-protected endpoints may return 403 if OTP codes are not echoed by the API (production behavior). The script still verifies public endpoints and OpenAPI coverage.
- `/places/external/suggestions` may return 500 until `APP_FOURSQUARE_API_KEY` is provided in Secrets Manager (`circles/app-config`).
- Once the Foursquare key is added and, if desired, OTP debug is enabled in config, re-run the verification to see additional 200s for auth flows.

## Component inventory (from Terraform)

- VPC

  - CIDR: `10.0.0.0/16`
  - Public subnets: `10.0.1.0/24`, `10.0.2.0/24`
  - Private subnets: `10.0.11.0/24`, `10.0.12.0/24`
  - NAT gateway: 1 (single NAT)

- ALB

  - Internet-facing, port 80 (HTTP)
  - Idle timeout: 180s
  - Target group: port 8000, health check path `/health`

- ECS Fargate

  - Cluster: `circles-cluster`
  - Service: `circles-svc` (desired count: 2)
  - Task definition: `circles-task` (Fargate/awsvpc)
  - Container: port 8000
  - Logs: CloudWatch `/ecs/circles`, retention 30 days
  - Networking: private subnets, no public IP; SG allows 8000 from ALB SG

- ECR

  - Repository: `circles-app`
  - Image tag default: `latest`
  - Build architecture: linux/amd64 (required for ECS Fargate x86_64)

- RDS PostgreSQL

  - Engine: Postgres 15
  - Instance class (default): `db.t4g.small`
  - Allocated storage: 20 GiB
  - Multi-AZ: false
  - Publicly accessible: false
  - Subnet group: private subnets
  - SG: ingress only from ECS tasks SG

- S3

  - Bucket: `circles-media-<suffix>`
  - Versioning: enabled
  - Deletion protection: disabled (`force_destroy = true` for dev)

- Secrets Manager

  - Secret name: `circles/app-config`
  - Keys: `APP_JWT_SECRET_KEY`, `APP_OTP_SECRET_KEY`, `APP_METRICS_TOKEN`, `APP_DATABASE_URL`, `S3_BUCKET`, `S3_REGION`
  - ECS task has policy to read this secret

- CloudWatch

  - Log group: `/ecs/circles`
  - Retention: 30 days

- DNS/TLS
  - Not configured by default (variables `domain_name` and `subdomain` exist but default empty)
  - Public access via HTTP only at `alb_dns_name`

## Sizing defaults and how to change

- App tasks (per task): CPU `512` (0.5 vCPU), memory `1024` MiB — from `variables.tf` (`container_cpu`, `container_memory`)
- App tasks (service): desired count `2` — from `variables.tf` (`desired_count`)
- Database: storage `20` GiB and instance class `db.t4g.small` — from `main.tf` and `variables.tf` (`db_instance_class`)
- Logs: 30 days retention — from `main.tf`
- Networking: one NAT GW; ALB on port 80 open to `0.0.0.0/0` and `::/0`

Change these by editing `infra/terraform/variables.tf` (for variables) or `infra/terraform/main.tf` (for fixed attributes like allocated storage) and re-running:

```bash
cd infra/terraform
terraform plan && terraform apply
```

## Public access and HTTPS

- The ALB is public on HTTP port 80. Mobile browsers often force HTTPS; use the explicit `http://` URL or configure a domain and ACM certificate to enable HTTPS (443 listener) with an HTTP→HTTPS redirect.

## AWS architecture and rationale

### Goals and constraints

- Move fast with a managed, low-ops stack (no EC2 management).
- Public HTTP entrypoint; support WebSockets; clean path to HTTPS + domain.
- Private compute and database; outbound internet for the app; simple media storage.
- First deploy is dev/staging-friendly; upgrade path to production hardening without redesign.

### Why each component

- VPC, subnets, route tables
  - Why: Network isolation and blast-radius control. Public subnets host the ALB only; private subnets host compute and database.
  - Trade-off: Adds NAT egress cost and complexity, but keeps services off the public internet.
- NAT Gateway (single)
  - Why: Lets private ECS tasks reach the internet for package installs, APIs (Foursquare/OSM), etc.
  - Trade-off: Per-hour + data processing costs; for prod, consider 1 NAT per AZ for HA.
- Application Load Balancer (ALB)
  - Why: HTTP/1.1 and HTTP/2 support, WebSockets, health checks, path-based routing, easy blue/green via target groups.
  - Trade-off: Slightly higher cost than NLB; simpler than API Gateway for session-based/websocket apps.
- ECS on Fargate
  - Why: Serverless containers (no EC2 to patch/scale). Native integration with ALB, IAM, CloudWatch, Secrets Manager.
  - Trade-off: Per-vCPU/GB cost; fewer daemon/sidecar patterns than EC2, but sufficient here.
- ECR
  - Why: Private, regional container registry close to ECS; IAM-integrated.
  - Trade-off: None significant vs Docker Hub for private workloads.
- RDS PostgreSQL 15 (with PostGIS enabled at DB level)
  - Why: Managed Postgres with automated backups, point-in-time restore; PostGIS for geospatial queries.
  - Trade-off: Higher cost than self-managed; we avoid undifferentiated heavy lifting.
- S3 (media)
  - Why: Durable, cheap object storage for avatars/photos; integrates with CDN if/when added.
  - Trade-off: Requires presigned flows or server-side proxy; here app writes directly with IAM.
- Secrets Manager
  - Why: Centralized secret storage with rotation, audit, and IAM access control; injects into ECS task env.
  - Trade-off: Minor per-secret cost; far simpler and safer than baking into images or env files.
- IAM
  - Why: Least-privilege policies granting ECS task only what it needs (Secrets read, S3 access, logs).
  - Trade-off: Requires careful scoping; Terraform codifies it.
- CloudWatch Logs
  - Why: Centralized stdout/stderr, retention control, easy AWS Console access and alarms.
  - Trade-off: Log ingress costs; mitigated with retention and sampling in the app.

### Security model

- Public ALB on 80 today (HTTP). ECS tasks and RDS are private-only.
- Security Groups:
  - ALB SG: inbound 80 from 0.0.0.0/0 and ::/0; outbound all.
  - ECS SG: inbound 8000 from ALB SG only; outbound all (via NAT).
  - RDS SG: inbound 5432 from ECS SG only; no public access.
- Secrets never committed; stored in Secrets Manager; Terraform state kept out of git.

### Sizing defaults and scaling

- ECS task: 0.5 vCPU (512) and 1 GiB (1024 MiB). Service desired count: 2 (simple HA behind ALB).
- RDS: `db.t4g.small`, 20 GiB storage.
- Scale up options:
  - ECS: Target-tracking autoscaling on CPU/Memory; increase desired count or task size.
  - RDS: Increase instance class, enable Multi-AZ, raise storage/IOPS; add read replicas if needed.
  - ALB: Scales automatically; can add WAF for protection.

### Trade-offs and alternatives considered

- API Gateway + Lambda: great for request/response APIs, but websockets/stateful background tasks and FastAPI app container fit ECS better.
- EC2 Auto Scaling: more control but more ops; Fargate eliminates node management.
- EKS (Kubernetes): powerful, but operationally heavier than needed here.
- NLB: cheaper L4, but lacks HTTP routing, health checks semantics, and websockets convenience.

### Production hardening checklist

- HTTPS + domain:
  - Add Route53 hosted zone and ACM certificate.
  - Add ALB HTTPS (443) listener with certificate and 80→443 redirect.
- High availability:
  - ECS service across 2+ AZs (already by subnets).
  - RDS Multi-AZ and automated backups; set deletion protection.
- Resilience/observability:
  - Auto scaling policies for ECS; health alarms (ALB 5xx, target unhealthy count, CPU/mem high).
  - RDS CPU/lag/storage alarms; disk auto-scaling if needed.
  - ALB access logs to S3; optional WAF for L7 protections.
- Security:
  - Tighten IAM policies (S3 path-level, secret ARNs specific).
  - Rotate secrets; consider KMS CMKs for S3 and RDS storage encryption.
- Cost controls:
  - Right-size ECS tasks; sleep non-prod at night; enable S3 lifecycle; monitor NAT data processing.

### CI/CD and deployments

- Build and push to ECR with linux/amd64 (Fargate x86_64):
  - `docker buildx build --platform linux/amd64 -t "$ECR_URL:latest" -f Dockerfile . --push`
- Deploy:
  - `aws ecs update-service --cluster circles-cluster --service circles-svc --force-new-deployment`
- Blue/green:
  - Introduce a second target group and weighted listeners, or use CodeDeploy for ECS.

### Environments

- Variables in `infra/terraform/variables.tf` control sizing and counts.
- For shared state across collaborators, move to S3 backend + DynamoDB locks and run `terraform init -migrate-state`.

### Known behaviors

- Without `APP_FOURSQUARE_API_KEY` in Secrets Manager, `/places/external/suggestions` may return 500.
- Mobile browsers may force HTTPS; until a cert/domain is configured, use the explicit `http://` ALB URL.

## Deploying code updates (AWS)

When code changes are ready, build an amd64 image and redeploy the ECS service:

```bash
# From repo root
AWS_REGION=$(cd infra/terraform && terraform output -raw aws_region)
ECR_URL=$(cd infra/terraform && terraform output -raw ecr_repository_url)

# Build x86_64 image for Fargate and push
docker buildx build --platform linux/amd64 -t "$ECR_URL:latest" -f Dockerfile . --push

# Roll ECS to pull the new image
aws ecs update-service \
  --cluster circles-cluster \
  --service circles-svc \
  --force-new-deployment \
  --region "$AWS_REGION"
```

Notes:

- The service pulls the image tag defined in the task definition (default `latest`).
- Any change to env or secrets requires a new task revision (via Terraform) and a service redeploy.

## Managing secrets and configuration (AWS only)

All sensitive config is stored in AWS Secrets Manager and injected into the ECS task at runtime. No local secrets are required.

Secret store:

- Name: `circles/app-config`
- Typical keys: `APP_JWT_SECRET_KEY`, `APP_OTP_SECRET_KEY`, `APP_METRICS_TOKEN`, `APP_DATABASE_URL`, `S3_BUCKET`, `S3_REGION`, and optional `APP_FOURSQUARE_API_KEY`.

Two supported ways to add/update secrets:

1. Infrastructure-as-Code (preferred)

- Add the key/value in `infra/terraform/secrets.tf` under `aws_secretsmanager_secret_version.app.secret_string`.
- Ensure the ECS task definition exposes it via `secrets` in `infra/terraform/main.tf`, e.g.:

```hcl
secrets = [
  { name = "APP_FOURSQUARE_API_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:APP_FOURSQUARE_API_KEY::" },
]
```

- Apply and redeploy:

```bash
cd infra/terraform
terraform apply -auto-approve
aws ecs update-service --cluster circles-cluster --service circles-svc --force-new-deployment --region "$(terraform output -raw aws_region)"
```

2. AWS Console (one-off)

- Open Secrets Manager → `circles/app-config` → Edit secret value → add/update the key (e.g., `APP_FOURSQUARE_API_KEY`).
- Then force a new ECS deployment to pick up the change:

```bash
AWS_REGION=$(cd infra/terraform && terraform output -raw aws_region)
aws ecs update-service --cluster circles-cluster --service circles-svc --force-new-deployment --region "$AWS_REGION"
```

Environment variables vs secrets:

- Non-sensitive toggles can be set in the ECS task `container_definitions.environment` (Terraform `main.tf`).
- Sensitive values belong in Secrets Manager and should be consumed via `secrets` in the task definition.

Reminder:

- Terraform state can contain secret values; keep tfstate out of git and prefer an encrypted remote backend (S3 + DynamoDB locks) for collaboration.

## Approximate monthly cost (us-east-1)

Assumes 730 hrs/mo, minimal traffic, defaults in Terraform; excludes internet egress and NAT data processing.

- ECS Fargate (2 tasks, 0.5 vCPU/1 GiB each): ~$36/mo
- ALB (hourly + baseline 1 LCU): ~$22/mo
- NAT Gateway (1, hourly only): ~$33/mo
- RDS Postgres db.t4g.small: ~$24/mo
- RDS storage 20 GiB gp3: ~$1.6/mo
- S3 (media, 10 GiB stored): ~$0.23/mo
- CloudWatch Logs (1 GiB ingest + storage): ~$0.53/mo
- Secrets Manager (1 secret): ~$0.40/mo
- ECR storage (0.5 GiB): ~$0.05/mo

Estimated baseline total: ~ $118/month

Notes/variables:

- NAT data processing ~$0.045/GB, ALB LCUs scale with requests/bandwidth, RDS Multi‑AZ and backups increase cost.
- Savings: set `desired_count=1` in non‑prod, add VPC endpoints for S3/Secrets to reduce NAT data, right‑size RDS and ECS.

---

## Feature algorithms, fallbacks, and configuration

This section documents how core features work, what signals they use, and all fallback paths and toggles. It also distinguishes between what is configurable at runtime (via env/secrets) and what is baked into the code.

### Trending places

- Primary endpoint(s):

  - `GET /places/trending` (time-windowed; defaults to last 24h)
  - `GET /places/trending/global` (fixed last 7d)

- Internal scoring (when using internal trending):

  - Windowed over time parameter.
  - Score = (check‑ins × 3) + (reviews × 2) + (photos × 1) + (unique users × 2).
  - Requires any activity in the window; otherwise no internal results.

- Foursquare-based override/fallback:

  - Override: if enabled, always use Foursquare v3 search as "trending" proxy (popularity-biased) and require `lat,lng`.
  - Fallback: if internal trending returns 0 items and fallback is enabled, fetch Foursquare results (also requires `lat,lng`).
  - Implementation uses `GET v3/places/search` with `ll`, `radius`, `limit`, and attempts `sort=POPULARITY` when supported by tenant.
  - Returns lightweight place objects (name, coords, categories, rating if available). These may not exist in our DB yet.

Data provenance during trending:

- Internal trending (DB only): all fields come from our tables (Places/CheckIns/Reviews/Photos). No external calls.
- FSQ override/fallback: items come from FSQ `places/search`:

  - name/coords/categories/rating from FSQ.
  - Not saved by default; shown as external suggestions in trending payload.
  - If an internal Place matches by proximity/name later, future results will be sourced from DB and enriched as needed.

- Configurables:

  - `APP_FSQ_TRENDING_OVERRIDE` (bool): if true, always use FSQ trending proxy (requires `lat,lng`). Default: true (can be set per environment).
  - `APP_FSQ_TRENDING_ENABLED` (bool): if true, allows fallback to FSQ when internal trending is empty. Default: true.
  - `APP_FSQ_TRENDING_RADIUS_M` (int): FSQ query radius in meters. Default: 5000.
  - `APP_FOURSQUARE_API_KEY` (secret): required for non-demo usage.

- Business behavior:
  - Override provides consistent results in greenfield regions without in-app activity.
  - Fallback ensures no "empty state" while our network effects ramp up.
  - Operators can disable override in mature markets to prefer internal social signals.

### Place suggestions (typeahead)

- Endpoint: `GET /places/search/suggestions`.
- Purpose: lightweight suggestions for cities, neighborhoods, categories and nearby places.
- Behavior:
  - If `lat,lng` provided, uses in-DB search within a configurable radius (PostGIS if enabled) and returns suggestions.
  - If not, uses OSM Nominatim for general text suggestions.

Data sources:

- With `lat,lng`: our DB Places (OSM seeded and/or FSQ-enriched) sorted by distance; categories/address from DB.
- Without `lat,lng`: OSM Nominatim returns display_name/coords; we map to suggestion shape (not persisted).

- Configurables:
  - `APP_EXTERNAL_SUGGESTIONS_RADIUS_M` (default 10,000 m).
  - `APP_USE_POSTGIS` (bool) to enable spatial queries.
- Business behavior:
  - Designed for fast, low-payload UI typeaheads; not intended to return full place cards.
  - Legacy alternative endpoints are hidden from Swagger to avoid confusion.

### Place enrichment (Foursquare)

- Purpose: improve place quality with phone, hours, rating, counts, and photos.
- Triggers:
  - On-demand endpoints (e.g., `GET /places/{id}/enrich`).
  - Automatic enrichment in `search/enhanced` (hidden from docs) and other flows when stale or missing data is detected.
- Signals and TTLs:
  - "Hot" places get a shorter enrichment TTL; defaults: hot 14 days, cold 60 days.
  - Matching uses name similarity + distance threshold.
- Configurables:
  - `APP_ENRICH_TTL_HOT_DAYS`, `APP_ENRICH_TTL_COLD_DAYS`.
  - `APP_ENRICH_MAX_DISTANCE_M` (match radius for FSQ linking).
  - `APP_ENRICH_MIN_NAME_SIM` (name similarity threshold).
  - `APP_FOURSQUARE_API_KEY` (secret) to enable enrichment.
- Business behavior:
  - Higher data quality improves discovery and ranking.
  - Enrichment respects rate limits and caches responses.

#### Data provenance (fields and sources)

When fields are missing in our DB, enrichment attempts to fill them:

- From OpenStreetMap (OSM Overpass seed):

  - name, latitude, longitude, categories (derived from tags), address, city
  - phone (if present in tags), website (if present), opening_hours (metadata)
  - external*id: `osm*<type>\_<id>`, data_source: `osm_overpass`

- From Foursquare (v3):
  - rating (venue details)
  - phone (tel), website
  - hours (display)
  - stats: total_ratings, total_photos, total_tips (stored in metadata)
  - photos: first N photo URLs (constructed from prefix/suffix)
  - categories (names)
  - fsq_id (stored in metadata and/or external_id)

Field precedence (on update):

1. Keep existing non-null DB fields unless enrichment provides higher-quality data (e.g., normalized phone/website).
2. Merge metadata; never drop existing keys without explicit logic.
3. Set `last_enriched_at` to track staleness TTL.

If a place does not exist in OSM seed but appears via FSQ (e.g., trending override):

- The response item originates from FSQ and is not immediately persisted.
- Metadata contains `discovery_source=foursquare` and may include stats and category labels.
- If promoted to DB later (future feature), we would set `external_id=fsq_id` and `data_source=foursquare` and backfill core fields from FSQ details.

### Check-ins and proximity enforcement

- Endpoint(s): `POST /checkins` and related list endpoints.
- Enforcement:
  - Optionally require user to be within a maximum distance of the place to check in.
  - Calculated via PostGIS geography or Haversine fallback.
- Configurables:
  - `APP_CHECKIN_ENFORCE_PROXIMITY` (bool).
  - `APP_CHECKIN_MAX_DISTANCE_METERS` (default 500 m).
- Business behavior:
  - Balances authenticity with ease of use; can be disabled in development or pilot programs.

### Authentication (phone-only OTP)

- Endpoints:
  - `POST /onboarding/request-otp` → returns `{ message }` and in debug also `{ otp }`.
  - `POST /onboarding/verify-otp` → returns token and user payload.
- OTP rate limiting (configurable):
  - Requests: 5-minute cooldown per phone (if enabled).
  - Verification attempts: per-minute and 5-minute burst limits (if enabled).
- Configurables:
  - `APP_OTP_RATE_LIMIT_ENABLED` (bool): default false.
  - `APP_OTP_REQUESTS_PER_MINUTE` (int): verification per-minute limit.
  - `APP_OTP_REQUESTS_BURST` (int): verification burst over 5 minutes.
  - `APP_OTP_EXPIRY_MINUTES` (default 10).
  - `APP_DEBUG` (bool): when true, echo OTP in response (dev/staging only).
- Business behavior:
  - Phone-only onboarding reduces friction and aligns with SMS-based auth.
  - Debug echo is never intended for production.

### Direct messages (DMs)

- REST + WebSocket (typing indicators, presence).
- Request flow: request/accept modeled like Instagram; creation by `recipient_id` only (no email paths).
- Rate limits:
  - `APP_DM_REQUESTS_PER_MIN`.
  - `APP_DM_MESSAGES_PER_MIN`.
- Business behavior:
  - Privacy: DM privacy respected when listing or initiating conversations.
  - Inbox search excludes email and uses name/username only.

### Activity feed and names

- Display names:
  - Prefer `user.name` if present; otherwise fallback to `User {id}` (email removed project-wide).
- Feed endpoints aggregate recent actions from followed users.
- Business behavior:
  - Keeps PII minimal and consistent with phone-only identity.

### Files and uploads

- Avatars and check-in photos stored in local dev or S3 in AWS.
- Configurables:
  - `APP_STORAGE_BACKEND`: `local` or `s3`.
  - Size caps: `APP_AVATAR_MAX_MB`, `APP_PHOTO_MAX_MB`.

### What is configurable vs fixed

- Configurable via env (non-sensitive):

  - Debug modes, PostGIS usage, proximity enforcement, FSQ trending flags, suggestion radius, timeouts, upload limits, DM limits.
  - All keys are listed in `.env.example`.

- Configurable via Secrets Manager (sensitive):

  - `APP_DATABASE_URL`, `APP_JWT_SECRET_KEY`, `APP_OTP_SECRET_KEY`, `APP_METRICS_TOKEN`, `APP_FOURSQUARE_API_KEY`, S3 credentials (if used).

- Fixed in code (change requires deploy):
  - Trending internal scoring weights.
  - Username and phone validation rules.
  - Enrichment TTL defaults (can be overridden via env), matching logic and category heuristics.

## Business rules and feature behaviors

### Onboarding

- Phone-only OTP flow; email paths removed/hidden.
- `OnboardingUserSetup` accepts an optional `interests` list; empty list allowed.
- Username constraints: 3–30 characters, alphanumeric + underscore.

### Discovery

- Trending prioritizes social activity; FSQ override/fallback can ensure non-empty lists in new geographies.
- Suggestions are light-weight and intended for fast UI experiences; not a substitute for full search results.

### Privacy and safety

- User display name fallbacks avoid exposing emails; private info minimized.
- Check-in proximity enforcement (when enabled) helps reduce spoofing.
- Rate limits across OTP and DMs mitigate abuse.

### Operations (AWS toggles)

- Debugging in AWS:
  - `APP_DEBUG=true` enables returning OTP in responses (dev/staging only). Controlled in ECS task `environment` in Terraform.
- Rolling out trending behavior:
  - Use `APP_FSQ_TRENDING_OVERRIDE=true` to rely on FSQ while the network grows; disable when internal activity is sufficient.
- Region expansion:
  - FSQ enrichment and override ensure data quality in new regions; keep `APP_FOURSQUARE_API_KEY` set.

---

## Quick reference: environment variables

- Core:
  - `APP_DEBUG`, `APP_DATABASE_URL`, `APP_USE_POSTGIS`, `APP_STORAGE_BACKEND`
- OTP:
  - `APP_OTP_SECRET_KEY` (secret), `APP_OTP_EXPIRY_MINUTES`, `APP_OTP_RATE_LIMIT_ENABLED`, `APP_OTP_REQUESTS_PER_MINUTE`, `APP_OTP_REQUESTS_BURST`
- JWT:
  - `APP_JWT_SECRET_KEY` (secret), `APP_JWT_ALGORITHM`, `APP_JWT_EXPIRY_MINUTES`
- DM:
  - `APP_DM_REQUESTS_PER_MIN`, `APP_DM_MESSAGES_PER_MIN`
- Foursquare/Discovery:
  - `APP_FOURSQUARE_API_KEY` (secret)
  - `APP_FSQ_TRENDING_ENABLED`, `APP_FSQ_TRENDING_OVERRIDE`, `APP_FSQ_TRENDING_RADIUS_M`
  - `APP_EXTERNAL_SUGGESTIONS_RADIUS_M`
- Timeouts/Uploads:
  - `APP_HTTP_TIMEOUT_SECONDS`, `APP_OVERPASS_TIMEOUT_SECONDS`, `APP_WS_SEND_TIMEOUT_SECONDS`
  - `APP_AVATAR_MAX_MB`, `APP_PHOTO_MAX_MB`
- S3:
  - `APP_S3_BUCKET`, `APP_S3_REGION`, `APP_S3_ENDPOINT_URL`, `APP_S3_ACCESS_KEY_ID`, `APP_S3_SECRET_ACCESS_KEY`, `APP_S3_PUBLIC_BASE_URL`, `APP_S3_USE_PATH_STYLE`
- Metrics/Logging:
  - `APP_METRICS_TOKEN` (secret), `APP_LOG_SAMPLE_RATE`
