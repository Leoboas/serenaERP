import time
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.api.licitacoes import router as licitacoes_router
from app.api.relatorios import router as relatorios_router
from app.core.config import get_settings
from app.core.observability import configure_logging, log_event
from app.infrastructure.persistence.session import engine
from app.infrastructure.redis import get_redis

settings = get_settings()
configure_logging()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(licitacoes_router)
app.include_router(relatorios_router)


def _request_correlation_id(request: Request) -> UUID:
    supplied = request.headers.get("X-Request-ID")
    if supplied:
        try:
            return UUID(supplied)
        except ValueError:
            # Do not reflect an arbitrary value into logs or response headers.
            pass
    return uuid4()


@app.middleware("http")
async def request_observability(request: Request, call_next) -> Response:
    correlation_id = _request_correlation_id(request)
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    response: Response | None = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if response is not None:
            response.headers["X-Request-ID"] = str(correlation_id)
        log_event(
            "http_request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code if response is not None else 500,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
            tenant_id=getattr(request.state, "tenant_id", None),
        )


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness only: the process can answer HTTP."""

    return {"status": "ok", "service": settings.app_name}


@app.get("/ready", tags=["system"])
async def readiness() -> Response:
    """Readiness: dependencies needed by the request path are reachable."""

    redis = None
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        redis = await get_redis()
        await redis.ping()
    except Exception:
        log_event("readiness_failed", level=40)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    finally:
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:
                log_event("readiness_redis_close_failed", level=30)
    return JSONResponse(content={"status": "ready", "service": settings.app_name})
