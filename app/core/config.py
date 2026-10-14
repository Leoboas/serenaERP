from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "goverp-core-ai"
    environment: Literal["development", "staging", "production"] = "production"
    database_url: str = "postgresql+asyncpg://goverp:goverp@localhost:5432/goverp"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    default_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    aws_region: str = "us-east-1"
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    # Tenant identity is carried by the Cognito ID token. The app client does
    # not grant callers permission to edit this immutable attribute.
    cognito_token_use: Literal["id", "access"] = "id"
    jwks_cache_ttl_seconds: int = Field(default=3600, ge=1)
    analysis_job_max_retries: int = Field(default=5, ge=0)
    # The execution lease must outlive Celery's fixed 120-second hard limit;
    # otherwise the relay can redeliver while a task is still allowed to run.
    analysis_job_lock_timeout_seconds: int = Field(default=300, ge=121)
    analysis_dispatch_interval_seconds: int = Field(default=30, ge=1)

    @property
    def cognito_issuer(self) -> str:
        return f"https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}"

    @property
    def cognito_jwks_url(self) -> str:
        return f"{self.cognito_issuer}/.well-known/jwks.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
