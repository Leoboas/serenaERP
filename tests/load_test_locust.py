"""Carga HTTP multi-tenant para validar capacidade e autoscaling do ECS.

Exemplo:
    locust -f tests/load_test_locust.py --host=https://api.example.com

Defina LOCUST_TENANT_IDS como UUIDs separados por vírgula e
LOCUST_ACCESS_TOKEN com um access token Cognito de teste. O teste não cria
credenciais nem usa tokens de produção.
"""

import os
from itertools import cycle

from locust import HttpUser, between, task


class GoverpUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        tenant_ids = [
            tenant.strip()
            for tenant in os.getenv("LOCUST_TENANT_IDS", "").split(",")
            if tenant.strip()
        ]
        if not tenant_ids:
            raise RuntimeError("LOCUST_TENANT_IDS deve conter pelo menos um UUID de tenant")
        self.tenants = cycle(tenant_ids)
        self.access_token = os.getenv("LOCUST_ACCESS_TOKEN", "")
        if not self.access_token:
            raise RuntimeError("LOCUST_ACCESS_TOKEN deve ser um token Cognito de teste")

    @task(5)
    def list_licitacoes(self) -> None:
        tenant_id = next(self.tenants)
        self.client.get(
            "/api/v1/licitacoes/",
            headers={"Authorization": f"Bearer {self.access_token}", "X-Tenant-ID": tenant_id},
            name="GET /api/v1/licitacoes/",
        )

    @task(2)
    def read_report(self) -> None:
        tenant_id = next(self.tenants)
        self.client.get(
            "/api/v1/relatorios/gastos-totais",
            headers={"Authorization": f"Bearer {self.access_token}", "X-Tenant-ID": tenant_id},
            name="GET /api/v1/relatorios/gastos-totais",
        )
