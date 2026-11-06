FROM python:3.12-slim

WORKDIR /service

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    pydantic \
    pydantic-settings \
    httpx \
    numpy \
    scipy \
    pyarrow

COPY app ./app

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
