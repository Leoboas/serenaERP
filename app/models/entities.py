"""Compatibility facade; ORM models live in infrastructure.persistence."""

from app.infrastructure.persistence.models import LicitacaoModel as Licitacao
from app.infrastructure.persistence.models import TenantModel as Tenant

__all__ = ["Licitacao", "Tenant"]
