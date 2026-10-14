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

output "ecs_scheduler_service_name" {
  value = module.ecs.scheduler_service_name
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}

output "ecs_migration_task_definition_arn" {
  value = module.ecs.migration_task_definition_arn
}

output "ecs_api_task_definition_arn" {
  value = module.ecs.api_task_definition_arn
}

output "ecs_worker_task_definition_arn" {
  value = module.ecs.worker_task_definition_arn
}

output "ecs_scheduler_task_definition_arn" {
  value = module.ecs.scheduler_task_definition_arn
}

output "ecs_service_security_group_id" {
  value = module.ecs.service_security_group_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

