locals {
  name_prefix        = "${var.project_name}-${var.environment}"
  encoded_auth_token = urlencode(var.auth_token)
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${local.name_prefix}-redis"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = local.name_prefix
  description                = "Celery broker and API cache"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.node_type
  port                       = 6379
  num_cache_clusters         = var.num_cache_clusters
  automatic_failover_enabled = var.multi_az_enabled
  multi_az_enabled           = var.multi_az_enabled
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  kms_key_id                 = var.kms_key_arn
  auth_token                 = var.auth_token
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [var.security_group_id]
}

resource "aws_secretsmanager_secret" "this" {
  name       = "${local.name_prefix}/redis"
  kms_key_id = var.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id = aws_secretsmanager_secret.this.id
  secret_string = jsonencode({
    host               = aws_elasticache_replication_group.this.primary_endpoint_address
    port               = 6379
    auth_token         = var.auth_token
    url                = "rediss://:${local.encoded_auth_token}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
    cache_url          = "rediss://:${local.encoded_auth_token}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
    celery_broker_url  = "rediss://:${local.encoded_auth_token}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/1"
    celery_backend_url = "rediss://:${local.encoded_auth_token}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/2"
  })
}
