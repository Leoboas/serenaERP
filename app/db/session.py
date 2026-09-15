"""Legacy import path for the infrastructure session adapter."""

from app.infrastructure.persistence.session import AsyncSessionLocal, engine, get_db_session

__all__ = ["AsyncSessionLocal", "engine", "get_db_session"]
