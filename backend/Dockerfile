FROM ghcr.io/astral-sh/uv:0.12.21 AS uv

FROM python:3.12.16-slim-bookworm
COPY --from=uv /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# Build with --build-arg EXTRAS="--extra voice" for local speech-to-text and text-to-speech.
ARG EXTRAS=""
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev $EXTRAS
COPY app ./app
COPY kb ./kb
RUN useradd --create-home app && mkdir -p data && chown app data
USER app
ENV PATH=/app/.venv/bin:$PATH FASTEMBED_CACHE_PATH=/app/data/fastembed HF_HOME=/app/data/hf
EXPOSE 8600
HEALTHCHECK --interval=15s --timeout=3s --start-period=600s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8600/api/health')"
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8600"]
