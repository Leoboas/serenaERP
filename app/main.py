from fastapi import FastAPI

from app.api.licitacoes import router as licitacoes_router
from app.api.relatorios import router as relatorios_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(licitacoes_router)
app.include_router(relatorios_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
