FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

RUN useradd --system --uid 10001 ibvap && mkdir -p /app/data && chown ibvap /app/data
USER ibvap

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "ibvap_core.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
