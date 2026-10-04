# Build with the repository root as context; both architectures use native official bases.
FROM python:3.13.12-slim-bookworm@sha256:a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6 AS gateway-build
COPY --from=ghcr.io/astral-sh/uv:0.11.0@sha256:e49fde5daf002023f0a2e2643861ce9ca8a8da5b73d0e6db83ef82ff99969baf /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY catalog ./catalog
RUN uv sync --locked --no-dev --no-editable

FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS console-build
WORKDIR /console
ENV NEXT_TELEMETRY_DISABLED=1
COPY admin-console/package.json admin-console/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY admin-console ./
RUN ADMIN_API_URL=http://127.0.0.1:18091 ADMIN_CONSOLE_ORIGIN=http://localhost:3000 ADMIN_CONSOLE_SESSION_SECRET=synthetic-build-placeholder-at-least-32-bytes npm run build
# Node needs these two native runtime libraries; preserve an architecture-neutral destination.
RUN mkdir /node-libs && cp /usr/lib/*-linux-gnu/libstdc++.so.6 /node-libs/ && cp /lib/*-linux-gnu/libgcc_s.so.1 /node-libs/

FROM python:3.13.12-slim-bookworm@sha256:a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6
ARG DEMO_SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision=$DEMO_SOURCE_REVISION
RUN useradd --system --uid 10001 --create-home demo
WORKDIR /app
COPY --from=gateway-build /app/.venv /app/.venv
COPY --from=console-build /usr/local/bin/node /usr/local/bin/node
COPY --from=console-build /node-libs/ /usr/local/lib/
COPY --from=console-build --chown=demo:demo /console/.next/standalone ./console/
COPY --from=console-build --chown=demo:demo /console/.next/static ./console/.next/static
COPY --from=console-build /console/node_modules/zod ./console/node_modules/zod
COPY admin-console/lib/config-schema.mjs admin-console/lib/demo-role.mjs ./console/lib/
COPY admin-console/scripts/bootstrap.mjs admin-console/scripts/docker-start.mjs admin-console/scripts/client-address.mjs admin-console/scripts/request-address.mjs ./console/scripts/
COPY alembic.ini ./
COPY migrations ./migrations
COPY catalog ./catalog
COPY loadtest/fake_provider ./loadtest/fake_provider
COPY scripts/seed_demo.py scripts/demo_traffic.py ./scripts/
COPY deploy/demo/*.py ./deploy/demo/
# The owner staging context has a commit file; ordinary source builds do not.
COPY LICENSE BUILD_COMMIT* /app/build-meta/
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app LD_LIBRARY_PATH=/usr/local/lib PYTHONUNBUFFERED=1 NEXT_TELEMETRY_DISABLED=1 PORT=3000
USER demo
EXPOSE 3000
STOPSIGNAL SIGTERM
CMD ["python", "-m", "deploy.demo.supervisor"]
