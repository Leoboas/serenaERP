from collections.abc import AsyncIterator
from uuid import UUID

import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Tenant

TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
TENANT_B = UUID("00000000-0000-0000-0000-000000000002")


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def aclose(self) -> None:
        return None


@pytest_asyncio.fixture
async def client(monkeypatch) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = FakeRedis()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add_all(
            [
                Tenant(id=TENANT_A, name="Tenant A", schema_name="tenant_a"),
                Tenant(id=TENANT_B, name="Tenant B", schema_name="tenant_b"),
            ]
        )
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    async def get_fake_user(request: Request) -> dict[str, str]:
        return {
            "custom:tenant_id": request.headers.get("X-Test-User-Tenant", str(TENANT_A)),
            "sub": "test-user",
        }

    app.dependency_overrides[get_current_user] = get_fake_user
    async def get_fake_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr("app.api.licitacoes.get_redis", get_fake_redis)
    monkeypatch.setattr("app.api.relatorios.get_redis", get_fake_redis)
    monkeypatch.setattr("app.api.licitacoes.analisar_licitacao.delay", lambda _: None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    await engine.dispose()
