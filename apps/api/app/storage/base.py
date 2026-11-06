from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    """Provedor abstrato de armazenamento com isolamento de tenant."""

    @abstractmethod
    def upload(self, tenant_id: str, path: str, content: bytes) -> str:
        """Faz upload de conteúdo para o tenant. Retorna o identificador/caminho do arquivo."""
        pass

    @abstractmethod
    def download(self, tenant_id: str, path: str) -> bytes:
        """Baixa o conteúdo de um arquivo do tenant."""
        pass

    @abstractmethod
    def delete(self, tenant_id: str, path: str) -> bool:
        """Exclui um arquivo do tenant. Retorna True se o arquivo foi excluído."""
        pass

    @abstractmethod
    def exists(self, tenant_id: str, path: str) -> bool:
        """Verifica se o arquivo existe para o tenant."""
        pass

    @abstractmethod
    def get_local_path(self, tenant_id: str, path: str) -> Path:
        """Retorna o Path local para leitura direta por DuckDB, PyArrow ou motores estatísticos."""
        pass

    @abstractmethod
    def list_files(self, tenant_id: str, prefix: str = "") -> list[str]:
        """Lista os arquivos salvos para o tenant com o prefixo indicado."""
        pass
