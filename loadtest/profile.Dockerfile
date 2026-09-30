# Ephemeral profiling tooling; never installed into the production/project environment.
FROM llm-gateway:loadtest
USER root
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
RUN uv tool install py-spy==0.4.2
ENTRYPOINT ["uvx", "--offline", "py-spy"]
