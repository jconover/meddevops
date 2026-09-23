FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY . .
RUN uv sync --frozen --no-dev --no-editable --package api

RUN useradd --system --no-create-home app
USER app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "python -m api.migrate && exec uvicorn --factory api.app:create_app --host 0.0.0.0 --port 8000"]
