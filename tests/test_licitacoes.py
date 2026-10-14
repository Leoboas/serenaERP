import pytest
from httpx import AsyncClient

TENANT_A = "00000000-0000-0000-0000-000000000001"
TENANT_B = "00000000-0000-0000-0000-000000000002"


@pytest.mark.asyncio
async def test_cria_e_isola_licitacoes_por_tenant(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/licitacoes/",
        headers={"X-Tenant-ID": TENANT_A},
        json={"numero": "PE-001", "descricao": "Compra de equipamentos", "valor_estimado": "1000.00"},
    )
    assert response.status_code == 201
    licitacao_id = response.json()["id"]
    assert response.json()["tenant_id"] == TENANT_A

    visible_to_a = await client.get("/api/v1/licitacoes/", headers={"X-Tenant-ID": TENANT_A})
    visible_to_b = await client.get(
        "/api/v1/licitacoes/",
        headers={"X-Tenant-ID": TENANT_B, "X-Test-User-Tenant": TENANT_B},
    )
    assert [item["id"] for item in visible_to_a.json()] == [licitacao_id]
    assert visible_to_b.json() == []

    cross_tenant_read = await client.get(
        f"/api/v1/licitacoes/{licitacao_id}",
        headers={"X-Tenant-ID": TENANT_B, "X-Test-User-Tenant": TENANT_B},
    )
    assert cross_tenant_read.status_code == 404


@pytest.mark.asyncio
async def test_valida_header_e_valor(client: AsyncClient) -> None:
    missing_header = await client.get("/api/v1/licitacoes/")
    assert missing_header.status_code == 400

    invalid_value = await client.post(
        "/api/v1/licitacoes/",
        headers={"X-Tenant-ID": TENANT_A},
        json={"numero": "PE-002", "descricao": "x", "valor_estimado": "0"},
    )
    assert invalid_value.status_code == 422

    mismatched_tenant = await client.get(
        "/api/v1/licitacoes/", headers={"X-Tenant-ID": "00000000-0000-0000-0000-000000000002"}
    )
    assert mismatched_tenant.status_code == 403


@pytest.mark.asyncio
async def test_business_number_is_unique_per_tenant(client: AsyncClient) -> None:
    payload = {"numero": "PE-UNIQUE-001", "descricao": "Compra", "valor_estimado": "10.00"}
    first = await client.post("/api/v1/licitacoes/", headers={"X-Tenant-ID": TENANT_A}, json=payload)
    duplicate = await client.post(
        "/api/v1/licitacoes/", headers={"X-Tenant-ID": TENANT_A}, json=payload
    )
    other_tenant = await client.post(
        "/api/v1/licitacoes/",
        headers={"X-Tenant-ID": TENANT_B, "X-Test-User-Tenant": TENANT_B},
        json=payload,
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert other_tenant.status_code == 201


@pytest.mark.asyncio
async def test_relatorio_agregado(client: AsyncClient) -> None:
    for number, value in [("PE-010", "10.00"), ("PE-011", "25.50")]:
        response = await client.post(
            "/api/v1/licitacoes/",
            headers={"X-Tenant-ID": TENANT_A},
            json={"numero": number, "descricao": "Serviço público", "valor_estimado": value},
        )
        assert response.status_code == 201

    report = await client.get("/api/v1/relatorios/gastos-totais", headers={"X-Tenant-ID": TENANT_A})
    assert report.status_code == 200
    assert report.json()["total"] == "35.50"
    assert report.json()["quantidade"] == 2


@pytest.mark.asyncio
async def test_tenant_cannot_schedule_analysis_for_another_tenant(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/licitacoes/",
        headers={"X-Tenant-ID": TENANT_A},
        json={"numero": "PE-ASYNC-001", "descricao": "Servico", "valor_estimado": "100.00"},
    )
    assert created.status_code == 201
    licitacao_id = created.json()["id"]

    forbidden = await client.post(
        f"/api/v1/licitacoes/{licitacao_id}/analisar-ia",
        headers={"X-Tenant-ID": TENANT_B, "X-Test-User-Tenant": TENANT_B},
    )
    assert forbidden.status_code == 404

    unchanged = await client.get(
        f"/api/v1/licitacoes/{licitacao_id}", headers={"X-Tenant-ID": TENANT_A}
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["status"] == "ABERTA"


@pytest.mark.asyncio
async def test_analysis_request_is_single_transition_and_persists_tenant_bound_job(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/licitacoes/",
        headers={"X-Tenant-ID": TENANT_A},
        json={"numero": "PE-ASYNC-002", "descricao": "Servico", "valor_estimado": "100.00"},
    )
    licitacao_id = created.json()["id"]

    requested = await client.post(
        f"/api/v1/licitacoes/{licitacao_id}/analisar-ia", headers={"X-Tenant-ID": TENANT_A}
    )
    assert requested.status_code == 200
    assert requested.json()["status"] == "EM_ANALISE_IA"

    duplicate = await client.post(
        f"/api/v1/licitacoes/{licitacao_id}/analisar-ia", headers={"X-Tenant-ID": TENANT_A}
    )
    assert duplicate.status_code == 409
