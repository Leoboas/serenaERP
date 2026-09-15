output "vpc_id" {
  value = module.vpc.vpc_id
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_app_client_id" {
  value = module.cognito.app_client_id
}

output "rds_secret_arn" {
  value     = module.rds.secret_arn
  sensitive = true
}

output "redis_secret_arn" {
  value     = module.elasticache.secret_arn
  sensitive = true
}

output "alb_dns_name" {
  value = module.ecs.alb_dns_name
}

output "ecs_api_service_name" {
  value = module.ecs.api_service_name
}

output "ecs_worker_service_name" {
  value = module.ecs.worker_service_name
}

