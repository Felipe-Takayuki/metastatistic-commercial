FROM python:3.12-slim

WORKDIR /service

COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx stripe

COPY billing_service ./billing_service

EXPOSE 8007

CMD ["uvicorn", "billing_service.main:app", "--host", "0.0.0.0", "--port", "8007"]
