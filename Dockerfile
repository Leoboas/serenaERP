FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system serena && useradd --system --gid serena --create-home serena

COPY --chown=serena:serena pyproject.toml ./
COPY --chown=serena:serena app ./app
COPY --chown=serena:serena migrations ./migrations
COPY --chown=serena:serena alembic.ini ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && rm -rf /app/build \
    && chown -R serena:serena /app

USER serena
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS development

USER root
COPY --chown=serena:serena tests ./tests
RUN pip install --no-cache-dir ".[dev]" \
    && rm -rf /app/build \
    && chown -R serena:serena /app
USER serena

# A plain `docker build .` must yield the production runtime image. Local
# Compose explicitly opts into the development target for the test runner.
FROM runtime AS production

USER serena
