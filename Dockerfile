# Build stage: install locked dependencies into a virtualenv.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# Dependencies first, so this layer is cached until uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --locked --no-dev --no-editable

# Runtime stage: only the virtualenv, running as a non-root user.
FROM python:3.13-slim
RUN useradd --system --uid 10001 --no-create-home gateway
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/alembic.ini /app/alembic.ini
COPY --from=build /app/migrations /app/migrations
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER gateway
EXPOSE 8000
CMD ["uvicorn", "llm_gateway.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
