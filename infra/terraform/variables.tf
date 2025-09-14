variable "project" {
  type        = string
  description = "Project name prefix"
  default     = "circles"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnets" {
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnets" {
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "db_username" {
  type        = string
  description = "RDS master username"
  default     = "circles"
}

variable "db_password" {
  type        = string
  description = "RDS master password"
  sensitive   = true
}

variable "db_instance_class" {
  type        = string
  default     = "db.t4g.small"
}

variable "desired_count" {
  type        = number
  default     = 2
}

variable "container_cpu" {
  type        = number
  default     = 512
}

variable "container_memory" {
  type        = number
  default     = 1024
}

variable "ecr_image_tag" {
  type        = string
  default     = "latest"
}

variable "domain_name" {
  type        = string
  description = "Root domain (optional). If set, ACM + Route53 records will be created."
  default     = ""
}

variable "subdomain" {
  type        = string
  description = "Subdomain to use under domain_name (e.g., api)."
  default     = "api"
}

variable "certificate_arn" {
  type        = string
  description = "Existing ACM certificate ARN to use for HTTPS (optional). If set, HTTPS will use this certificate."
  default     = ""
}


