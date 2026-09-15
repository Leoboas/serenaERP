"""Compatibility exports for the public API dependency surface."""

from app.api.dependencies import get_current_user, get_tenant_id

__all__ = ["get_current_user", "get_tenant_id"]
