FROM python:3.12-slim

WORKDIR /service

COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings

COPY audit_service ./audit_service

EXPOSE 8008

CMD ["uvicorn", "audit_service.main:app", "--host", "0.0.0.0", "--port", "8008"]
