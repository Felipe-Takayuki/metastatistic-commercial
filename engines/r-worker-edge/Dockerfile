FROM python:3.12-slim
WORKDIR /edge
RUN pip install --no-cache-dir fastapi uvicorn httpx
COPY edge ./edge
EXPOSE 8090
CMD ["uvicorn", "edge.main:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8090"]
