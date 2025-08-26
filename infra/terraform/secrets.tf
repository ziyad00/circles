resource "aws_secretsmanager_secret" "app" {
  name = "${var.project}/app-config"
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    APP_JWT_SECRET_KEY  = random_password.jwt_secret.result,
    APP_OTP_SECRET_KEY  = random_password.otp_secret.result,
    APP_METRICS_TOKEN   = random_password.metrics_token.result,
    APP_DATABASE_URL    = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${module.rds.db_instance_endpoint}/${var.project}",
    S3_BUCKET           = aws_s3_bucket.media.bucket,
    S3_REGION           = var.aws_region
  })
}

data "aws_iam_policy_document" "ecs_task_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.app.arn]
  }
}

resource "aws_iam_role_policy" "ecs_task_secrets" {
  name   = "${var.project}-ecs-task-secrets"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_secrets.json
}


