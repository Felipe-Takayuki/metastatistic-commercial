"""Interface abstrata para motores estatísticos."""
from abc import ABC, abstractmethod
from typing import Any


class StatisticalEngine(ABC):
    """Interface abstrata base para execução estatística."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome do motor (ex.: 'python', 'r')."""
        pass

    @abstractmethod
    def supports(self, analysis: str) -> bool:
        """Indica se a análise informada é suportada nativamente pelo motor."""
        pass

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Verifica a saúde operacional do motor."""
        pass

    @abstractmethod
    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Executa a análise estatística e devolve resultado padronizado APA 7th.
        Estrutura de retorno:
        {
            "status": "complete",
            "results": {
                ".meta": [...],
                "table_name": {
                    "title": "...",
                    "schema": {"fields": [...]},
                    "data": [...],
                    "footnotes": [...]
                }
            }
        }
        """
        pass
