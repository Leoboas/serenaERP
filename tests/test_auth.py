from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api import dependencies
from app.infrastructure.auth import cognito
from app.infrastructure.auth.cognito import CognitoTokenVerifier

TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_development_token_uses_local_tenant_without_cognito() -> None:
    settings = SimpleNamespace(
        environment="development",
        default_tenant_id=TENANT_ID,
    )

    claims = await CognitoTokenVerifier(settings).verify("dev-token")

    assert claims == {
        "sub": "local-development-user",
        "custom:tenant_id": TENANT_ID,
    }


@pytest.mark.asyncio
async def test_cognito_jwt_and_tenant_claim(monkeypatch) -> None:
    settings = SimpleNamespace(
        environment="production",
        cognito_jwks_url="https://cognito.test/.well-known/jwks.json",
        cognito_issuer="https://cognito.test/pool",
        cognito_app_client_id="client-id",
        cognito_token_use="access",
        jwks_cache_ttl_seconds=3600,
    )
    monkeypatch.setattr(cognito, "get_settings", lambda: settings)
    cognito._jwks_cache.update(keys=[{"kid": "key-1"}], expires_at=9999999999)
    token = "signed-rs256-token"
    monkeypatch.setattr(cognito.jwt, "get_unverified_header", lambda _: {"kid": "key-1"})
    monkeypatch.setattr(cognito.jwt.PyJWK, "from_dict", lambda _: SimpleNamespace(key="public-key"))
    monkeypatch.setattr(
        cognito.jwt,
        "decode",
        lambda *args, **kwargs: {
            "iss": settings.cognito_issuer,
            "sub": "user-1",
            "client_id": settings.cognito_app_client_id,
            "token_use": "access",
            "custom:tenant_id": TENANT_ID,
        },
    )
    request = Request({"type": "http", "headers": []})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    user = await dependencies.get_current_user(request, credentials)
    tenant = await dependencies.get_tenant_id(TENANT_ID, user)

    assert user["sub"] == "user-1"
    assert tenant == UUID(TENANT_ID)
    assert request.state.user == user


@pytest.mark.asyncio
async def test_tenant_claim_mismatch_is_forbidden() -> None:
    with pytest.raises(HTTPException) as error:
        await dependencies.get_tenant_id(
            TENANT_ID,
            {"custom:tenant_id": "00000000-0000-0000-0000-000000000002"},
        )
    assert error.value.status_code == 403
