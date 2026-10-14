terraform {
  required_version = ">= 1.6.0"

  # Backend values are account-specific and intentionally live outside source.
  # Copy backend.hcl.example to an ignored backend.hcl before a real init.
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.64"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

provider "random" {}
