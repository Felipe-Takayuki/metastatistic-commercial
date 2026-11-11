from typing import Optional

from ..config import settings
from .base import StorageProvider
from .local import LocalStorageProvider
from .s3 import S3StorageProvider

_provider_instance: Optional[StorageProvider] = None


def get_storage_provider() -> StorageProvider:
    """Retorna uma instância única configurada do StorageProvider."""
    global _provider_instance
    if _provider_instance is None:
        backend = (getattr(settings, "storage_backend", "local") or "local").lower()
        if backend == "s3":
            _provider_instance = S3StorageProvider(
                bucket=getattr(settings, "s3_bucket", "metastatistic"),
                endpoint_url=getattr(settings, "s3_endpoint_url", "") or None,
                access_key=getattr(settings, "s3_access_key", "") or None,
                secret_key=getattr(settings, "s3_secret_key", "") or None,
                region=getattr(settings, "s3_region", "") or None,
                base_cache_dir=settings.data_dir,
                default_tenant_id=getattr(settings, "default_tenant_id", "default"),
            )
        else:
            _provider_instance = LocalStorageProvider(
                base_dir=settings.data_dir,
                default_tenant_id=getattr(settings, "default_tenant_id", "default"),
            )
    return _provider_instance


def reset_storage_provider() -> None:
    """Reseta a instância para facilitar testes."""
    global _provider_instance
    _provider_instance = None


__all__ = [
    "StorageProvider",
    "LocalStorageProvider",
    "S3StorageProvider",
    "get_storage_provider",
    "reset_storage_provider",
]
