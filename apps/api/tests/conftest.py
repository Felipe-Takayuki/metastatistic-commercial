import httpx
import pytest

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Cada teste usa um diretório de dados isolado."""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    return settings.data_dir


@pytest.fixture(autouse=True)
def fresh_analysis_service():
    """Cache de resultados e estado do pool são globais: cada teste começa do zero."""
    from app.analysis_service import reset_service

    reset_service()
    yield
    reset_service()


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def upload(client, csv_text: str, name: str = "vendas.csv"):
    r = await client.post("/datasets", files={"file": (name, csv_text.encode(), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


SALES_CSV = (
    "id,regiao,receita,nota,dia\n"
    "1,Sul,10.5,3,2024-01-01\n"
    "2,Sul,20.0,4,2024-01-02\n"
    "3,Norte,15.25,3,2024-01-03\n"
    "4,Norte,,5,2024-01-04\n"
)
