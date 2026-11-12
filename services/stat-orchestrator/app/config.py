from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    port: int = 8003
    host: str = "0.0.0.0"
    r_worker_urls: str = "http://localhost:8001"
    # Worker R em outra máquina (engines/r-worker-edge): token do edge e envio do Parquet antes da análise.
    r_worker_token: str = ""
    r_worker_sync_datasets: bool = False
    data_dir: Path = Path("/data")
    cache_size_mb: int = 64
    cache_max_entries: int = 256
    default_engine: str = "auto"
    analysis_timeout_s: float = 60.0
    max_concurrent_jobs: int = 4

    @property
    def worker_urls(self) -> list[str]:
        urls = [u.strip().rstrip("/") for u in self.r_worker_urls.split(",") if u.strip()]
        return urls or ["http://localhost:8001"]


settings = Settings()
