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
