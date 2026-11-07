import io
from pathlib import Path
import tempfile
import duckdb
from fastapi.testclient import TestClient
import pyarrow as pa
import pyarrow.ipc as ipc
import pyarrow.parquet as pq
import pytest

from app.config import settings
from app.main import app
from app.pii_masking import (
    apply_pii_masking,
    auto_detect_and_mask_pii,
    hash_sha256,
    mask_cpf,
    mask_email,
    mask_phone,
    redact,
)
from app.query_engine import (
    QueryEngineError,
    execute_query,
    execute_query_arrow_stream,
    validate_sql,
)
from app.schemas import PIIMaskRule, PrepStep

client = TestClient(app)


@pytest.fixture
def sample_parquet(tmp_path):
    table = pa.Table.from_arrays(
        [
            pa.array([1, 2, 3, 4, 5]),
            pa.array(["Alice Silva", "Bob Souza", "Charlie Pereira", "David Lima", "Eva Costa"]),
            pa.array(["alice@example.com", "bob@domain.org", "charlie@corp.com", "david@web.net", "eva@mail.io"]),
            pa.array(["12345678901", "98765432100", "11122233344", "55566677788", "99988877766"]),
            pa.array(["11987654321", "21988887777", "31977776666", "41966665555", "51955554444"]),
            pa.array([25, 32, 45, 19, 58]),
            pa.array([3500.50, 5200.00, 8900.75, 2100.00, 12000.00]),
        ],
        names=["id", "name", "email", "cpf", "phone", "age", "salary"],
    )
    pq_path = tmp_path / "patients.parquet"
    pq.write_table(table, pq_path)
    return pq_path


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "data-engine-service"
    assert "duckdb_version" in data
    assert "arrow_version" in data


def test_sqlglot_validation():
    # Queries válidas
    assert "SELECT 1" in validate_sql("SELECT 1;")
    assert "SELECT a, b FROM dataset WHERE a > 10" in validate_sql("SELECT a, b FROM dataset WHERE a > 10")

    # Rejeição de DDL/DML destrutivo
    with pytest.raises(QueryEngineError, match="Only read-only SELECT queries are allowed"):
        validate_sql("DROP TABLE users;")

    with pytest.raises(QueryEngineError, match="Only read-only SELECT queries are allowed"):
        validate_sql("DELETE FROM users WHERE id = 1;")

    # Rejeição de múltiplos statements
    with pytest.raises(QueryEngineError, match="Exactly one SQL statement"):
        validate_sql("SELECT 1; SELECT 2;")

    # Rejeição de table functions
    with pytest.raises(QueryEngineError, match="Table functions"):
        validate_sql("SELECT * FROM read_csv('secret.csv')")


def test_pii_masking_functions():
    assert mask_email("johndoe@example.com") == "j***e@example.com"
    assert mask_cpf("123.456.789-01") == "***.456.789-**"
    assert mask_cpf("12345678901") == "***.456.789-**"
    assert mask_phone("11987654321") == "(11) 9****-4321"
    assert redact("anything") == "[REDACTED]"

    # Hashing salgado por tenant
    h1 = hash_sha256("john_doe", salt="tenant_a")
    h2 = hash_sha256("john_doe", salt="tenant_b")
    assert h1 != h2
    assert len(h1) == 16


def test_auto_detect_pii():
    data = [
        {
            "id": 1,
            "name": "Maria Silva",
            "email": "maria@med.br",
            "cpf": "12345678900",
            "phone": "11987654321",
            "age": 30,
        }
    ]
    masked = auto_detect_and_mask_pii(data, tenant_id="t1")
    assert masked[0]["id"] == 1
    assert masked[0]["age"] == 30
    assert masked[0]["email"] == "m***a@med.br"
    assert masked[0]["cpf"] == "***.456.789-**"
    assert masked[0]["phone"] == "(11) 9****-4321"
    assert masked[0]["name"] != "Maria Silva"  # sha256 hash


def test_execute_query_and_parquet(sample_parquet, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(sample_parquet.parent))

    # Query simples
    res = execute_query(
        sql="SELECT id, name, age, salary FROM patients WHERE age > 20 ORDER BY age ASC",
        tenant_id="default",
        dataset_id="patients",
    )
    assert res.row_count == 4
    assert res.columns[0].name == "id"
    assert res.columns[2].measurementLevel == "scale"
    assert res.rows[0]["name"] == "Alice Silva"
    assert res.rows[0]["age"] == 25
    assert res.execution_time_ms >= 0


def test_execute_query_with_pii_masking(sample_parquet, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(sample_parquet.parent))

    res = execute_query(
        sql="SELECT id, name, email, cpf, phone, age FROM patients WHERE id = 1",
        tenant_id="tenant_x",
        dataset_id="patients",
        mask_pii=True,
    )
    assert res.row_count == 1
    row = res.rows[0]
    assert row["id"] == 1
    assert row["email"] == "a***e@example.com"
    assert row["cpf"] == "***.456.789-**"
    assert row["phone"] == "(11) 9****-4321"
    assert row["name"] != "Alice Silva"


def test_arrow_ipc_streaming(sample_parquet, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(sample_parquet.parent))

    stream_bytes = execute_query_arrow_stream(
        sql="SELECT id, name, salary FROM patients ORDER BY id ASC",
        tenant_id="default",
        dataset_id="patients",
    )
    assert isinstance(stream_bytes, bytes)
    assert len(stream_bytes) > 0

    # Reconstrói a tabela PyArrow a partir dos bytes IPC
    reader = ipc.open_stream(stream_bytes)
    table = reader.read_all()
    assert table.num_rows == 5
    assert table.column_names == ["id", "name", "salary"]
    assert table["id"][0].as_py() == 1


def test_api_query_endpoints(sample_parquet, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(sample_parquet.parent))

    # POST /queries/run
    response = client.post(
        "/queries/run",
        json={"sql": "SELECT id, name, age FROM patients WHERE id = 2", "dataset_id": "patients"},
        headers={"X-Tenant-ID": "test_tenant"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 1
    assert data["rows"][0]["name"] == "Bob Souza"

    # POST /queries/arrow
    response_arrow = client.post(
        "/queries/arrow",
        json={"sql": "SELECT id, name FROM patients", "dataset_id": "patients"},
        headers={"X-Tenant-ID": "test_tenant"},
    )
    assert response_arrow.status_code == 200
    assert response_arrow.headers["content-type"] == "application/vnd.apache.arrow.stream"

    # Valida payload Arrow reconstruído
    reader = ipc.open_stream(response_arrow.content)
    arrow_t = reader.read_all()
    assert arrow_t.num_rows == 5


def test_transform_preview_endpoint(sample_parquet, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(sample_parquet.parent))

    steps = [
        {"op": "select", "params": {"columns": ["id", "name", "age", "salary"]}},
        {"op": "filter", "params": {"condition": '"age" >= 30'}},
        {"op": "rename", "params": {"columns": {"salary": "renda"}}},
        {"op": "sort", "params": {"columns": ["age"], "ascending": False}},
    ]

    response = client.post(
        "/transforms/preview",
        json={"dataset_id": "patients", "steps": steps, "limit": 10},
        headers={"X-Tenant-ID": "default"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 3
    # Maior idade primeiro: 58 (Eva Costa)
    assert data["rows"][0]["name"] == "Eva Costa"
    assert data["rows"][0]["age"] == 58
    assert "renda" in data["rows"][0]
    assert "salary" not in data["rows"][0]


def test_connections_endpoints():
    # 1. Teste de conexão SQLite em memória
    test_req = {
        "connection": {
            "id": "sqlite_test_1",
            "tenant_id": "tenant_abc",
            "name": "SQLite In-Memory",
            "type": "sqlite",
            "database": ":memory:",
        }
    }
    resp = client.post("/connections/test", json=test_req)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert "Successfully connected" in res_data["message"]
    assert res_data["latency_ms"] is not None

    # 2. Registrar conexão
    conn_payload = {
        "id": "c1",
        "tenant_id": "tenant_abc",
        "name": "Production SQLite",
        "type": "sqlite",
        "database": ":memory:",
    }
    resp_create = client.post("/connections", json=conn_payload, headers={"X-Tenant-ID": "tenant_abc"})
    assert resp_create.status_code == 200
    assert resp_create.json()["id"] == "c1"

    # 3. Listar conexões
    resp_list = client.get("/connections", headers={"X-Tenant-ID": "tenant_abc"})
    assert resp_list.status_code == 200
    conns = resp_list.json()
    assert len(conns) == 1
    assert conns[0]["name"] == "Production SQLite"
