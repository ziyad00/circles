locals {
  name = var.project
}

resource "random_id" "suffix" {
  byte_length = 2
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.1.2"

  name = "${local.name}-vpc"
  cidr = var.vpc_cidr

  azs             = [for i in range(0, length(var.public_subnets)) : data.aws_availability_zones.available.names[i]]
  public_subnets  = var.public_subnets
  private_subnets = var.private_subnets

  enable_nat_gateway = true
  single_nat_gateway = true

  tags = { Project = local.name }
}

data "aws_availability_zones" "available" {}

resource "aws_ecr_repository" "app" {
  name                 = "${local.name}-app"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  tags = { Project = local.name }
}

resource "aws_s3_bucket" "media" {
  bucket = "${local.name}-media-${random_id.suffix.hex}"
  force_destroy = true
  tags = { Project = local.name }
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb-sg"
  description = "ALB SG"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

resource "aws_lb" "app" {
  name               = "${local.name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets
  idle_timeout       = 180
  tags = { Project = local.name }
}

resource "aws_lb_target_group" "app" {
  name        = "${local.name}-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 5
    timeout             = 5
    interval            = 15
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    # If a certificate is provided, redirect HTTP->HTTPS; otherwise forward to target group
    type = var.certificate_arn != "" ? "redirect" : "forward"
    dynamic "redirect" {
      for_each = var.certificate_arn != "" ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
    dynamic "forward" {
      for_each = var.certificate_arn == "" ? [1] : []
      content {
        target_group {
          arn = aws_lb_target_group.app.arn
        }
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn != "" ? 1 : 0
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"

  certificate_arn = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_security_group" "ecs_tasks" {
  name   = "${local.name}-ecs-sg"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name   = "${local.name}-rds-sg"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.5.3"

  identifier = "${local.name}-db"
  engine               = "postgres"
  engine_version       = "15"
  family               = "postgres15"
  allocated_storage    = 20
  instance_class       = var.db_instance_class
  db_name              = "${local.name}"
  username             = var.db_username
  password             = var.db_password
  manage_master_user_password = false

  multi_az             = false
  publicly_accessible  = false
  vpc_security_group_ids = [aws_security_group.rds.id]
  subnet_ids           = module.vpc.private_subnets
  create_db_subnet_group = true
  db_subnet_group_name   = aws_db_subnet_group.this.name
  skip_final_snapshot  = true
  deletion_protection  = false

  tags = { Project = local.name }
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name}-db-subnets"
  subnet_ids = module.vpc.private_subnets
  tags = { Project = local.name }
}

resource "aws_iam_role" "ecs_task" {
  name = "${local.name}-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "ecs-tasks.amazonaws.com" },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_exec" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "ecs_task_s3" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

resource "aws_ecs_cluster" "this" {
  name = "${local.name}-cluster"
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${local.name}-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.container_cpu
  memory                   = var.container_memory
  execution_role_arn       = aws_iam_role.ecs_task.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "app"
      image     = "${aws_ecr_repository.app.repository_url}:${var.ecr_image_tag}"
      essential = true
      portMappings = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "APP_DEBUG", value = "true" },
        { name = "APP_USE_POSTGIS", value = "true" },
        { name = "APP_STORAGE_BACKEND", value = "s3" },
        { name = "S3_BUCKET", value = aws_s3_bucket.media.bucket },
        { name = "S3_REGION", value = var.aws_region },
        { name = "APP_S3_BUCKET", value = aws_s3_bucket.media.bucket },
        { name = "APP_S3_REGION", value = var.aws_region },
        { name = "APP_JWT_EXPIRY_MINUTES", value = "20160" },
        { name = "APP_FSQ_TRENDING_OVERRIDE", value = "false" },
        { name = "APP_FSQ_TRENDING_ENABLED", value = "true" },
        { name = "APP_CHECKIN_MAX_DISTANCE_METERS", value = "1000" },
      ]
      secrets = [
        { name = "APP_JWT_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:APP_JWT_SECRET_KEY::" },
        { name = "APP_OTP_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:APP_OTP_SECRET_KEY::" },
        { name = "APP_METRICS_TOKEN", valueFrom = "${aws_secretsmanager_secret.app.arn}:APP_METRICS_TOKEN::" },
        { name = "APP_DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.app.arn}:APP_DATABASE_URL::" },
      ]
      command = ["sh", "-c", "uv run alembic upgrade heads && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
      logConfiguration = {
        logDriver = "awslogs",
        options = {
          awslogs-group         = "/ecs/${local.name}"
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "app"
        }
      }
    }
  ])
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${local.name}"
  retention_in_days = 30
}

resource "random_password" "jwt_secret" {
  length  = 48
  special = false
}

resource "random_password" "otp_secret" {
  length  = 48
  special = false
}

resource "random_password" "metrics_token" {
  length  = 32
  special = false
}

resource "local_file" "secrets" {
  filename = "../secrets.generated.env"
  content  = <<EOT
# Circles generated secrets (keep safe!)
AWS_REGION=${var.aws_region}
DB_HOST=${module.rds.db_instance_endpoint}
DB_NAME=${var.project}
DB_USER=${var.db_username}
DB_PASSWORD=${var.db_password}
APP_DATABASE_URL=postgresql+asyncpg://${var.db_username}:${var.db_password}@${module.rds.db_instance_endpoint}/${var.project}
APP_JWT_SECRET_KEY=${random_password.jwt_secret.result}
APP_OTP_SECRET_KEY=${random_password.otp_secret.result}
APP_METRICS_TOKEN=${random_password.metrics_token.result}
S3_BUCKET=${aws_s3_bucket.media.bucket}
S3_REGION=${var.aws_region}
EOT
  file_permission = "0600"
}

resource "aws_ecs_service" "app" {
  name            = "${local.name}-svc"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}

output "alb_dns_name" {
  value = aws_lb.app.dns_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "s3_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "rds_endpoint" {
  value = module.rds.db_instance_endpoint
}



# Optional: CloudFront in front of ALB to provide HTTPS without a custom domain
resource "aws_cloudfront_distribution" "alb" {
  enabled = true

  origin {
    domain_name = aws_lb.app.dns_name
    origin_id   = "alb-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "alb-origin"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = [
      "GET",
      "HEAD",
      "OPTIONS",
      "PUT",
      "PATCH",
      "POST",
      "DELETE",
    ]

    cached_methods = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      headers      = ["Authorization"]
      cookies { forward = "all" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  price_class = "PriceClass_100"

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { Project = local.name }
}

