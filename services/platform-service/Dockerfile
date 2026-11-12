# Contexto de build: ./services  (docker compose: build.context=./services, dockerfile=platform-service/Dockerfile)
FROM python:3.12-slim

WORKDIR /service
RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx stripe websockets python-docx

COPY audit-service/audit_service ./audit_service
COPY auth-tenant-service/auth_tenant_service ./auth_tenant_service
COPY billing-service/billing_service ./billing_service
COPY bi-report-service/bi_report_service ./bi_report_service
COPY export-service/export_service ./export_service
COPY platform-service/platform_service ./platform_service

ENV PYTHONPATH=/service
EXPOSE 8000
CMD ["uvicorn", "platform_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
