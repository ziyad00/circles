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
