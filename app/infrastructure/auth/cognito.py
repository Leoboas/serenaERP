import time
from typing import Any

import httpx
import jwt

from app.core.config import Settings, get_settings

_jwks_cache: dict[str, Any] = {"expires_at": 0.0, "keys": []}


class CognitoTokenVerifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def _get_jwks(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if _jwks_cache["expires_at"] > now:
            return _jwks_cache["keys"]
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self.settings.cognito_jwks_url)
            response.raise_for_status()
        keys = response.json().get("keys", [])
        _jwks_cache.update(keys=keys, expires_at=now + self.settings.jwks_cache_ttl_seconds)
        return keys

    async def verify(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        jwk = next(key for key in await self._get_jwks() if key.get("kid") == header.get("kid"))
        key = jwt.PyJWK.from_dict(jwk).key
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            issuer=self.settings.cognito_issuer,
            options={"verify_aud": False},
        )
        if claims.get("token_use") != self.settings.cognito_token_use:
            raise ValueError("tipo de token inválido")
        audience = (
            claims.get("client_id")
            if claims.get("token_use") == "access"
            else claims.get("aud")
        )
        if audience != self.settings.cognito_app_client_id:
            raise ValueError("audience inválida")
        if not claims.get("custom:tenant_id"):
            raise ValueError("tenant ausente no token")
        return claims


__all__ = ["CognitoTokenVerifier", "_jwks_cache"]
