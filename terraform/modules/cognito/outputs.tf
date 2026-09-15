output "user_pool_id" { value = aws_cognito_user_pool.this.id }
output "user_pool_arn" { value = aws_cognito_user_pool.this.arn }
output "app_client_id" { value = aws_cognito_user_pool_client.this.id }
output "application_secret_arn" { value = aws_secretsmanager_secret.application.arn }
output "issuer" { value = "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.this.id}" }

data "aws_region" "current" {}
