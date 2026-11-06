from pathlib import Path
from typing import Optional

from .base import StorageProvider


class LocalStorageProvider(StorageProvider):
    """Provedor de armazenamento local no disco com separação por tenant

    e suporte transparente à estrutura legada de datasets no tenant default.
    """

    def __init__(self, base_dir: Path | str, default_tenant_id: str = "default"):
        self.base_dir = Path(base_dir)
        self.default_tenant_id = default_tenant_id
        self.tenants_dir = self.base_dir / "tenants"
        self.legacy_datasets_dir = self.base_dir / "datasets"

    def _resolve_tenant_path(self, tenant_id: str, path: str) -> Path:
        clean_path = path.lstrip("/")
        return self.tenants_dir / tenant_id / clean_path

    def _resolve_legacy_path(self, path: str) -> Path:
        clean_path = path.lstrip("/")
        return self.legacy_datasets_dir / clean_path

    def upload(self, tenant_id: str, path: str, content: bytes) -> str:
        target = self._resolve_tenant_path(tenant_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)

    def download(self, tenant_id: str, path: str) -> bytes:
        local_path = self.get_local_path(tenant_id, path)
        if not local_path.is_file():
            raise FileNotFoundError(f"Arquivo '{path}' não encontrado para o tenant '{tenant_id}'.")
        return local_path.read_bytes()

    def delete(self, tenant_id: str, path: str) -> bool:
        deleted = False
        target = self._resolve_tenant_path(tenant_id, path)
        if target.is_file():
            target.unlink()
            deleted = True

        if tenant_id == self.default_tenant_id:
            legacy = self._resolve_legacy_path(path)
            if legacy.is_file():
                legacy.unlink()
                deleted = True

        return deleted

    def exists(self, tenant_id: str, path: str) -> bool:
        target = self._resolve_tenant_path(tenant_id, path)
        if target.is_file():
            return True
        if tenant_id == self.default_tenant_id:
            legacy = self._resolve_legacy_path(path)
            if legacy.is_file():
                return True
        return False

    def get_local_path(self, tenant_id: str, path: str) -> Path:
        target = self._resolve_tenant_path(tenant_id, path)
        if target.is_file():
            return target
        if tenant_id == self.default_tenant_id:
            legacy = self._resolve_legacy_path(path)
            if legacy.is_file():
                return legacy
        return target

    def list_files(self, tenant_id: str, prefix: str = "") -> list[str]:
        results: set[str] = set()
        clean_prefix = prefix.lstrip("/")

        tenant_root = self.tenants_dir / tenant_id
        if tenant_root.is_dir():
            for p in tenant_root.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(tenant_root).as_posix()
                    if rel.startswith(clean_prefix):
                        results.add(rel)

        if tenant_id == self.default_tenant_id and self.legacy_datasets_dir.is_dir():
            for p in self.legacy_datasets_dir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(self.legacy_datasets_dir).as_posix()
                    if rel.startswith(clean_prefix):
                        results.add(rel)

        return sorted(results)
