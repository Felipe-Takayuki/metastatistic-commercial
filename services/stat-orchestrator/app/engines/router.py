"""Roteador inteligente Dual-Engine (Python Engine B e R Worker Engine A)."""
from typing import Any

from app.config import settings
from app.engines.base import StatisticalEngine
from app.engines.python_engine import PythonStatisticalEngine
from app.engines.r_engine import RStatisticalEngine


class EngineRouter:
    """Roteador para seleção do motor estatístico ótimo."""

    def __init__(
        self,
        python_engine: PythonStatisticalEngine | None = None,
        r_engine: RStatisticalEngine | None = None,
    ):
        self.python_engine = python_engine or PythonStatisticalEngine()
        self.r_engine = r_engine or RStatisticalEngine()

    def select_engine(self, payload: dict[str, Any]) -> tuple[StatisticalEngine, str]:
        engine_req = (payload.get("engine") or settings.default_engine).lower().strip()
        analysis = payload.get("analysis", "")

        if engine_req in ("py", "python", "engine_b"):
            if not self.python_engine.supports(analysis):
                raise ValueError(
                    f"A análise '{analysis}' não é suportada pelo Engine B comercial (Python). "
                    f"Análises suportadas: {sorted(list(self.python_engine.SUPPORTED_ANALYSES))}"
                )
            return self.python_engine, "python"

        if engine_req in ("r", "r_worker", "engine_a"):
            return self.r_engine, "r"

        if engine_req == "auto":
            if self.python_engine.supports(analysis):
                return self.python_engine, "python"
            return self.r_engine, "r"

        raise ValueError(
            f"Modo de motor inválido: '{engine_req}'. Opções válidas: 'auto', 'py', 'r'."
        )

    async def execute(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
        engine, engine_name = self.select_engine(payload)
        result = await engine.execute(payload)
        return result, engine_name


default_router = EngineRouter()
