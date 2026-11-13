from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    r_worker_url: str = "http://localhost:8001"
    r_worker_urls: str = ""  # lista separada por vírgulas (o pool); vazio = usa só r_worker_url
    # Worker R em outra máquina (engines/r-worker-edge): token do edge e envio do Parquet antes da análise.
    r_worker_token: str = ""
    r_worker_sync_datasets: bool = False

    # Armazenamento e Multi-tenancy
    database_url: str = ""
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_bucket: str = "metastatistic"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "garage"  # o Garage só aceita a região do seu s3_region (padrão "garage"); AWS: us-east-1 etc.
    default_tenant_id: str = "default"


    # Análises: tempo limite imposto pelo worker (ele mata o motor se estourar), fila e cache
    analysis_timeout_s: float = 60.0
    analysis_queue_max: int = 20          # pessoas esperando além dos workers ocupados; acima disso => 429
    analysis_queue_wait_s: float = 90.0   # espera máxima na fila; acima disso => 503
    worker_down_s: float = 10.0           # quanto tempo um worker inalcançável fica fora de circulação
    analysis_cache_entries: int = 256
    analysis_cache_mb: int = 64

    # Datasets: Parquet (um por dataset) + registro SQLite. Volume compartilhado, somente leitura no worker R.
    data_dir: Path = Path("./data")
    max_upload_mb: int = 200

    # Execução de SQL do usuário
    query_row_limit: int = 10_000
    query_timeout_s: float = 30.0
    query_memory_limit: str = "1GB"
    query_threads: int = 2

    # Salvar consulta como dataset (resultado derivado: bloco, transformações…)
    derived_dataset_max_rows: int = 2_000_000
    derived_dataset_timeout_s: float = 120.0

    # SaaS: dataset novo nasce privado (só o dono e administradores leem) até o dono compartilhar em "Acesso…".
    # Desligado = comportamento antigo (aberto a todos que entraram). O docker-compose liga por padrão.
    datasets_private_by_default: bool = False

    # Autenticação: desligada por padrão (comportamento anterior: todos são administradores).
    # Ligada, tudo exige sessão; o primeiro acesso cria o administrador em POST /auth/setup.
    auth_enabled: bool = False
    session_ttl_hours: int = 24 * 7
    session_idle_hours: float = 12.0      # sem nenhuma requisição por tanto tempo a sessão cai (0 = desligado)
    cookie_secure: bool = False           # true atrás de HTTPS
    login_max_failures: int = 5           # falhas seguidas (por usuário) antes do bloqueio temporário
    login_lock_s: float = 60.0

    @property
    def worker_urls(self) -> list[str]:
        urls = [u.strip().rstrip("/") for u in self.r_worker_urls.split(",") if u.strip()]
        return urls or [self.r_worker_url.rstrip("/")]


settings = Settings()
