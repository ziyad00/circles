output "cloudfront_domain_name" {
  description = "CloudFront distribution domain (HTTPS)"
  value       = try(aws_cloudfront_distribution.alb.domain_name, null)
}

output "aws_region" {
  value = var.aws_region
}

output "codepipeline_name" {
  description = "Name of the CodePipeline"
  value       = aws_codepipeline.app.name
}

output "codebuild_project_name" {
  description = "Name of the CodeBuild project"
  value       = aws_codebuild_project.app.name
}

output "github_connection_arn" {
  description = "GitHub connection ARN (needs to be activated)"
  value       = aws_codestarconnections_connection.github.arn
}

