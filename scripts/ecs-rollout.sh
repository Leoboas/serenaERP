#!/usr/bin/env bash
# Run a schema-gated ECS rollout. Terraform registers task definitions, but the
# ECS services intentionally ignore task_definition drift; this script is the
# only supported path that promotes them.
set -euo pipefail

export AWS_PAGER=""

require() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
}

command -v aws >/dev/null || {
  echo "AWS CLI v2 is required." >&2
  exit 2
}

for variable in \
  ECS_CLUSTER \
  ECS_PRIVATE_SUBNET_IDS \
  ECS_SERVICE_SECURITY_GROUP_ID \
  ECS_MIGRATION_TASK_DEFINITION \
  ECS_API_SERVICE \
  ECS_API_TASK_DEFINITION \
  ECS_WORKER_SERVICE \
  ECS_WORKER_TASK_DEFINITION \
  ECS_SCHEDULER_SERVICE \
  ECS_SCHEDULER_TASK_DEFINITION; do
  require "$variable"
done

network_configuration="awsvpcConfiguration={subnets=[${ECS_PRIVATE_SUBNET_IDS}],securityGroups=[${ECS_SERVICE_SECURITY_GROUP_ID}],assignPublicIp=DISABLED}"

echo "Starting one migration task in cluster ${ECS_CLUSTER}."
task_arn="$(aws ecs run-task \
  --cluster "$ECS_CLUSTER" \
  --launch-type FARGATE \
  --task-definition "$ECS_MIGRATION_TASK_DEFINITION" \
  --network-configuration "$network_configuration" \
  --count 1 \
  --query 'tasks[0].taskArn' \
  --output text)"

if [[ -z "$task_arn" || "$task_arn" == "None" ]]; then
  echo "ECS did not return a migration task ARN; services were not updated." >&2
  exit 1
fi

aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER" --tasks "$task_arn"
exit_codes="$(aws ecs describe-tasks \
  --cluster "$ECS_CLUSTER" \
  --tasks "$task_arn" \
  --query 'tasks[0].containers[].exitCode' \
  --output text)"

if [[ -z "$exit_codes" || "$exit_codes" == "None" ]]; then
  echo "Migration task stopped without a container exit code; refusing rollout." >&2
  exit 1
fi

for exit_code in $exit_codes; do
  if [[ "$exit_code" != "0" ]]; then
    echo "Migration task failed (exit code ${exit_code}); refusing rollout." >&2
    exit 1
  fi
done

roll_service() {
  local service="$1"
  local task_definition="$2"
  echo "Promoting ${service} after successful migration."
  aws ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$service" \
    --task-definition "$task_definition" \
    --force-new-deployment \
    --no-cli-pager >/dev/null
  aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "$service"
}

roll_service "$ECS_API_SERVICE" "$ECS_API_TASK_DEFINITION"
roll_service "$ECS_WORKER_SERVICE" "$ECS_WORKER_TASK_DEFINITION"
roll_service "$ECS_SCHEDULER_SERVICE" "$ECS_SCHEDULER_TASK_DEFINITION"

echo "Schema-gated rollout completed successfully."
