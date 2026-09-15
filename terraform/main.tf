resource "random_password" "db" {
  length  = 32
  special = true
}

resource "random_password" "redis_auth" {
  length  = 32
  special = false
}

module "vpc" {
  source             = "./modules/vpc"
  project_name       = var.project_name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  nat_gateway_count  = var.environment == "staging" ? 1 : 2
}

module "cognito" {
  source       = "./modules/cognito"
  project_name = var.project_name
}

module "rds" {
  source              = "./modules/rds"
  project_name        = var.project_name
  db_name             = var.db_name
  db_username         = var.db_username
  db_password         = random_password.db.result
  db_instance_class   = var.environment == "staging" ? "db.t4g.micro" : var.db_instance_class
  multi_az            = var.environment == "prod"
  deletion_protection = var.environment == "prod"
  private_subnet_ids  = module.vpc.private_subnet_ids
  security_group_id   = module.vpc.database_security_group_id
  kms_key_arn         = module.vpc.data_kms_key_arn
}

module "elasticache" {
  source             = "./modules/elasticache"
  project_name       = var.project_name
  private_subnet_ids = module.vpc.private_subnet_ids
  security_group_id  = module.vpc.redis_security_group_id
  auth_token         = random_password.redis_auth.result
  kms_key_arn        = module.vpc.data_kms_key_arn
  node_type          = var.environment == "staging" ? "cache.t4g.micro" : "cache.r7g.large"
  num_cache_clusters = var.environment == "staging" ? 1 : 2
  multi_az_enabled   = var.environment == "prod"
}

module "ecs" {
  source             = "./modules/ecs"
  project_name       = var.project_name
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  api_image          = var.api_image
  worker_image       = var.worker_image
  db_secret_arn      = module.rds.secret_arn
  redis_secret_arn   = module.elasticache.secret_arn
  cognito_secret_arn = module.cognito.application_secret_arn
  certificate_arn    = var.certificate_arn
  domain_name        = var.domain_name
}

resource "aws_budgets_budget" "monthly" {
  count        = var.budget_alert_email == "" ? 0 : 1
  name         = "${var.project_name}-${var.environment}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}

