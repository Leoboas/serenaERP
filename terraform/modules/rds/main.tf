resource "aws_db_subnet_group" "this" {
  name       = "${var.project_name}-db"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "this" {
  identifier                = var.project_name
  engine                    = "postgres"
  engine_version            = "15.10"
  instance_class            = var.db_instance_class
  allocated_storage         = 100
  max_allocated_storage     = 1000
  storage_type              = "gp3"
  storage_encrypted         = true
  kms_key_id                = var.kms_key_arn
  multi_az                  = var.multi_az
  db_name                   = var.db_name
  username                  = var.db_username
  password                  = var.db_password
  port                      = 5432
  db_subnet_group_name      = aws_db_subnet_group.this.name
  vpc_security_group_ids    = [var.security_group_id]
  backup_retention_period   = 7
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-final"
  publicly_accessible       = false
  apply_immediately         = false
}

resource "aws_secretsmanager_secret" "this" {
  name       = "${var.project_name}/rds"
  kms_key_id = var.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id = aws_secretsmanager_secret.this.id
  secret_string = jsonencode({
    host     = aws_db_instance.this.address
    port     = aws_db_instance.this.port
    dbname   = var.db_name
    username = var.db_username
    password = var.db_password
    url      = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${var.db_name}"
  })
}
