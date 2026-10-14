locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

resource "aws_cognito_user_pool" "this" {
  name                     = "${local.name_prefix}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 1
  }

  schema {
    name                     = "tenant_id"
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = false
    required                 = true
    string_attribute_constraints {
      min_length = 36
      max_length = 36
    }
  }

  # Tenant assignment is an authorization boundary. Accounts are provisioned
  # through an authenticated administrative workflow, never self-registered
  # with a caller-controlled tenant UUID.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_user_pool_client" "this" {
  name                          = "${local.name_prefix}-api"
  user_pool_id                  = aws_cognito_user_pool.this.id
  generate_secret               = true
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"
  read_attributes               = ["email", "custom:tenant_id"]
  write_attributes              = ["email"]
  access_token_validity         = 60
  id_token_validity             = 60
  refresh_token_validity        = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_secretsmanager_secret" "application" {
  name = "${local.name_prefix}/cognito"
}

resource "aws_secretsmanager_secret_version" "application" {
  secret_id = aws_secretsmanager_secret.application.id
  secret_string = jsonencode({
    AWS_REGION            = data.aws_region.current.region
    COGNITO_USER_POOL_ID  = aws_cognito_user_pool.this.id
    COGNITO_APP_CLIENT_ID = aws_cognito_user_pool_client.this.id
    # Cognito emits immutable user attributes such as tenant_id in ID tokens.
    # A pre-token Lambda would be required to put it in access tokens.
    COGNITO_TOKEN_USE = "id"
  })
}
