import pytest
from pathlib import Path
from app.storage import LocalStorageProvider, get_storage_provider, reset_storage_provider
from app.config import settings


def test_local_storage_basic_lifecycle(tmp_path: Path):
    provider = LocalStorageProvider(base_dir=tmp_path)
    tenant_id = "tenant-abc"
    filename = "data/raw.csv"
    content = b"col1,col2\n1,2\n3,4"

    # Upload
    res_path = provider.upload(tenant_id, filename, content)
    assert Path(res_path).is_file()
    assert provider.exists(tenant_id, filename)

    # Download
    downloaded = provider.download(tenant_id, filename)
    assert downloaded == content

    # Get local path
    local_path = provider.get_local_path(tenant_id, filename)
    assert local_path.is_file()
    assert local_path.read_bytes() == content

    # List files
    files = provider.list_files(tenant_id)
    assert "data/raw.csv" in files

    files_prefixed = provider.list_files(tenant_id, prefix="data/")
    assert "data/raw.csv" in files_prefixed

    files_empty = provider.list_files(tenant_id, prefix="other/")
    assert len(files_empty) == 0

    # Delete
    deleted = provider.delete(tenant_id, filename)
    assert deleted is True
    assert not provider.exists(tenant_id, filename)

    with pytest.raises(FileNotFoundError):
        provider.download(tenant_id, filename)


def test_tenant_isolation(tmp_path: Path):
    provider = LocalStorageProvider(base_dir=tmp_path)
    file_rel = "dataset.parquet"

    provider.upload("tenant_1", file_rel, b"content-for-tenant-1")
    provider.upload("tenant_2", file_rel, b"content-for-tenant-2")

    assert provider.download("tenant_1", file_rel) == b"content-for-tenant-1"
    assert provider.download("tenant_2", file_rel) == b"content-for-tenant-2"

    provider.delete("tenant_1", file_rel)
    assert not provider.exists("tenant_1", file_rel)
    assert provider.exists("tenant_2", file_rel)


def test_default_tenant_legacy_fallback(tmp_path: Path):
    # Simula estrutura antiga onde datasets ficavam em data_dir / "datasets" / "sample.parquet"
    legacy_dir = tmp_path / "datasets"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / "sample.parquet"
    legacy_file.write_bytes(b"legacy-parquet-data")

    provider = LocalStorageProvider(base_dir=tmp_path, default_tenant_id="default")

    # O arquivo legado deve ser reconhecido pelo tenant default
    assert provider.exists("default", "sample.parquet")
    assert provider.download("default", "sample.parquet") == b"legacy-parquet-data"
    assert provider.get_local_path("default", "sample.parquet") == legacy_file
    assert "sample.parquet" in provider.list_files("default")

    # Mas outro tenant não enxerga o dataset legado do default
    assert not provider.exists("tenant_x", "sample.parquet")


def test_get_storage_provider_singleton(monkeypatch, tmp_path: Path):
    reset_storage_provider()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "storage_backend", "local")

    p1 = get_storage_provider()
    p2 = get_storage_provider()
    assert p1 is p2
    assert isinstance(p1, LocalStorageProvider)

    reset_storage_provider()
