FROM python:3.12-slim

WORKDIR /service

COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx

COPY auth_tenant_service ./auth_tenant_service

EXPOSE 8002

CMD ["uvicorn", "auth_tenant_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
