# Circles AWS Terraform (ECS Fargate + RDS + ALB + ECR + S3)

This module provisions a production-ready baseline on AWS:

- VPC with public (ALB) and private (ECS/RDS) subnets and a NAT gateway
- Application Load Balancer (ALB)
- ECS Fargate cluster, task, and service
- RDS PostgreSQL 15 (enable PostGIS extension after create)
- ECR repository for container images
- S3 bucket for media (versioned)
- CloudWatch logs

## Prerequisites

- Terraform >= 1.5
- AWS credentials configured (env or profile)
- Built application image pushed to ECR (see Deploy section)

## Variables

- project: name prefix (default: circles)
- aws_region: region (default: us-east-1)
- db_username: RDS username (default: circles)
- db_password: RDS password (no default; pass via TF_VAR_db_password)
- ecr_image_tag: ECR image tag to deploy (default: latest)

## Usage

```bash
cd infra/terraform
export TF_VAR_db_password='strong-password'
terraform init
terraform apply -auto-approve
```

Outputs include:

- alb_dns_name (HTTP and HTTPS)
- ecr_repository_url
- s3_bucket
- rds_endpoint

## PostGIS

After RDS is created, connect and enable PostGIS once:

```bash
psql "postgresql://<user>:<pass>@<rds-endpoint>:5432/circles" -c "CREATE EXTENSION IF NOT EXISTS postgis; SELECT PostGIS_Version();"
```

## Build & Deploy image to ECR

```bash
# Get ECR repo URL from output
REPO=$(terraform output -raw ecr_repository_url)

# Authenticate Docker to ECR
aws ecr get-login-password --region $(terraform output -raw aws_region 2>/dev/null || echo us-east-1) \
| docker login --username AWS --password-stdin ${REPO%/*}

# Build, tag, push
docker build -t circles:prod .
docker tag circles:prod $REPO:latest
docker push $REPO:latest

# Update ECS service to pull new image
aws ecs update-service --cluster circles-cluster --service circles-svc --force-new-deployment
```

## Configuration in Task Definition

The task sets:

- APP_USE_POSTGIS=true
- APP_STORAGE_BACKEND=s3
- S3_BUCKET=<created bucket>

Set remaining env and secrets (e.g., APP_DATABASE_URL, APP_JWT_SECRET_KEY) in the task definition or via Parameters/Secrets Manager. Recommended: use AWS Secrets Manager and map into the task.

## HTTPS

Provide an ACM certificate ARN to enable HTTPS on the ALB (with HTTP -> HTTPS redirect):

```bash
cd infra/terraform
export TF_VAR_db_password='strong-password'
export TF_VAR_certificate_arn='arn:aws:acm:us-east-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
terraform apply -auto-approve
```

If you don't have a certificate, create one in ACM (in us-east-1) and validate via DNS, then set `TF_VAR_certificate_arn`.

Alternatively, enable CloudFront (auto-HTTPS, no custom domain required). After apply, use the CloudFront domain output.

```bash
terraform apply -auto-approve
# Look for the CloudFront domain in outputs and use https://<cf-domain>/
```

## Notes

- ALB listener is HTTP by default; front it with ACM + HTTPS in production.
- Auto-seeding: consider disabling in production and run controlled jobs.
- WebSockets: ALB idle timeout set to 180s; adjust as needed.
- Scaling: adjust desired_count and configure autoscaling policies.
