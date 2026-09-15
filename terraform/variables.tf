variable "aws_region" {
  type        = string
  description = "AWS region for the platform"
  default     = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "goverp-core-ai"
}

variable "environment" {
  type    = string
  default = "prod"

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment deve ser staging ou prod."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "A plataforma exige exatamente duas Availability Zones."
  }
}

variable "nat_gateway_count" {
  type    = number
  default = 2

  validation {
    condition     = var.nat_gateway_count >= 1 && var.nat_gateway_count <= 2
    error_message = "nat_gateway_count deve ser 1 ou 2."
  }
}

variable "db_name" {
  type    = string
  default = "goverp"
}

variable "db_username" {
  type    = string
  default = "goverp_admin"
}

variable "db_instance_class" {
  type    = string
  default = "db.r7g.large"
}

variable "budget_alert_email" {
  type        = string
  description = "E-mail para alertas do AWS Budget."
  default     = ""
}

variable "budget_limit_usd" {
  type    = number
  default = 200

  validation {
    condition     = var.budget_limit_usd > 0
    error_message = "O limite do budget deve ser maior que zero."
  }
}

variable "api_image" {
  type    = string
  default = "goverp-core-ai:latest"
}

variable "worker_image" {
  type    = string
  default = "goverp-core-ai:latest"
}

variable "certificate_arn" {
  type    = string
  default = ""
}

variable "domain_name" {
  type    = string
  default = "api.goverp.example.com"
}

