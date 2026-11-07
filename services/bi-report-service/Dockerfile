FROM python:3.12-slim

WORKDIR /service

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

COPY . .

ENV PORT=8005
ENV DATA_DIR=/data
EXPOSE 8005

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8005}"]
