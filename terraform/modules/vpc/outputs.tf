output "vpc_id" { value = aws_vpc.this.id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "database_security_group_id" { value = aws_security_group.database.id }
output "redis_security_group_id" { value = aws_security_group.redis.id }
output "data_kms_key_arn" { value = aws_kms_key.data.arn }
