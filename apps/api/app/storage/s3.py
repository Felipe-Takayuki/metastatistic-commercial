from pathlib import Path
from typing import Optional

from .base import StorageProvider


def _is_missing(exc: Exception) -> bool:
    """O erro do boto3 é "chave não existe" (e não falha de rede, credencial ou bucket)?"""
    error = (getattr(exc, "response", None) or {}).get("Error", {})
    return error.get("Code") in {"NoSuchKey", "404", "NotFound"}


class S3StorageProvider(StorageProvider):
    """Provedor de armazenamento em S3 / MinIO compatível, com cache local

    para leitura direta via DuckDB/Parquet e isolamento por tenant.
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        base_cache_dir: Path | str = "./data",
        default_tenant_id: str = "default",
    ):
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.cache_dir = Path(base_cache_dir) / "s3_cache"
        self.default_tenant_id = default_tenant_id
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise RuntimeError(
                    "O pacote 'boto3' é obrigatório para utilizar S3StorageProvider. "
                    "Instale-o via 'pip install boto3' ou use o backend local."
                )

            from botocore.config import Config

            kwargs = {}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
                # Garage/MinIO: endereçamento por caminho (http://host/bucket/chave), sem DNS por bucket; e checksums só
                # quando o S3 exige (o boto3 recente manda CRC por padrão, o que servidores compatíveis nem sempre aceitam)
                kwargs["config"] = Config(
                    s3={"addressing_style": "path"},
                    request_checksum_calculation="when_required",
                    response_checksum_validation="when_required",
                )
            if self.region:
                kwargs["region_name"] = self.region
            if self.access_key and self.secret_key:
                kwargs["aws_access_key_id"] = self.access_key
                kwargs["aws_secret_access_key"] = self.secret_key

            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _resolve_key(self, tenant_id: str, path: str) -> str:
        clean_path = path.lstrip("/")
        return f"tenants/{tenant_id}/{clean_path}"

    def upload(self, tenant_id: str, path: str, content: bytes) -> str:
        client = self._get_client()
        key = self._resolve_key(tenant_id, path)
        client.put_object(Bucket=self.bucket, Key=key, Body=content)

        # Atualiza o cache local
        local_target = self.cache_dir / "tenants" / tenant_id / path.lstrip("/")
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_bytes(content)

        return f"s3://{self.bucket}/{key}"

    def download(self, tenant_id: str, path: str) -> bytes:
        client = self._get_client()
        key = self._resolve_key(tenant_id, path)
        try:
            resp = client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except Exception as e:
            # Só "objeto inexistente" vira FileNotFoundError; falha de rede/credencial/bucket sobe como está
            if not _is_missing(e):
                raise
            # Fallback para chave sem prefixo de tenant no default tenant
            if tenant_id == self.default_tenant_id:
                try:
                    resp = client.get_object(Bucket=self.bucket, Key=f"datasets/{path.lstrip('/')}")
                    return resp["Body"].read()
                except Exception:
                    pass
            raise FileNotFoundError(f"Arquivo '{path}' não encontrado no S3 para o tenant '{tenant_id}': {e}")

    def delete(self, tenant_id: str, path: str) -> bool:
        client = self._get_client()
        key = self._resolve_key(tenant_id, path)
        existed = self.exists(tenant_id, path)
        if existed:
            client.delete_object(Bucket=self.bucket, Key=key)
            if tenant_id == self.default_tenant_id:
                try:
                    client.delete_object(Bucket=self.bucket, Key=f"datasets/{path.lstrip('/')}")
                except Exception:
                    pass

            local_target = self.cache_dir / "tenants" / tenant_id / path.lstrip("/")
            if local_target.is_file():
                local_target.unlink()
            return True
        return False

    def exists(self, tenant_id: str, path: str) -> bool:
        client = self._get_client()
        key = self._resolve_key(tenant_id, path)
        try:
            client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            if tenant_id == self.default_tenant_id:
                try:
                    client.head_object(Bucket=self.bucket, Key=f"datasets/{path.lstrip('/')}")
                    return True
                except Exception:
                    pass
            return False

    def get_local_path(self, tenant_id: str, path: str) -> Path:
        local_target = self.cache_dir / "tenants" / tenant_id / path.lstrip("/")
        if not local_target.is_file():
            content = self.download(tenant_id, path)
            local_target.parent.mkdir(parents=True, exist_ok=True)
            local_target.write_bytes(content)
        return local_target

    def list_files(self, tenant_id: str, prefix: str = "") -> list[str]:
        client = self._get_client()
        clean_prefix = prefix.lstrip("/")
        full_prefix = f"tenants/{tenant_id}/{clean_prefix}"
        paginator = client.get_paginator("list_objects_v2")
        results: set[str] = set()

        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel = key.replace(f"tenants/{tenant_id}/", "", 1)
                results.add(rel)

        if tenant_id == self.default_tenant_id:
            legacy_prefix = f"datasets/{clean_prefix}"
            for page in paginator.paginate(Bucket=self.bucket, Prefix=legacy_prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    rel = key.replace("datasets/", "", 1)
                    results.add(rel)

        return sorted(results)
