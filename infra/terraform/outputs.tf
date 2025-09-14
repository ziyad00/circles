output "cloudfront_domain_name" {
  description = "CloudFront distribution domain (HTTPS)"
  value       = try(aws_cloudfront_distribution.alb.domain_name, null)
}

output "aws_region" {
  value = var.aws_region
}


