FROM ghcr.io/astral-sh/uv:0.9.7 AS uv
FROM python:3.11-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 WHISPER_MODEL_PATH=/models/small \
    OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && useradd --uid 10001 --no-create-home whisper
COPY server.py ./
USER 10001:10001
EXPOSE 8000
CMD [".venv/bin/uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
