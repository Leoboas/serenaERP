variable "project_name" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "security_group_id" { type = string }
variable "auth_token" {
  type      = string
  sensitive = true
}
variable "kms_key_arn" { type = string }
variable "node_type" { type = string }
variable "num_cache_clusters" { type = number }
variable "multi_az_enabled" { type = bool }
