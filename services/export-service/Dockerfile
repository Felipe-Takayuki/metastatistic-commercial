FROM python:3.12-slim

WORKDIR /service

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

COPY . .

ENV PORT=8006
ENV TEMP_DIR=/tmp/export
EXPOSE 8006

CMD ["sh", "-c", "uvicorn export_service.main:app --host 0.0.0.0 --port ${PORT:-8006}"]
