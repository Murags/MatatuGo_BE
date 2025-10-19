FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

COPY api/ ./api/


EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
